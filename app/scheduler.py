from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from .models import now_iso
from .runner import run_suite
from .store import read_state, update_state

BUSY = {"job_id": "", "terminal_id": ""}
_STARTED = False


def _parse(dt: str) -> datetime | None:
    if not dt:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(dt, fmt)
        except ValueError:
            continue
    return None


def next_run_at(job: dict, from_time: datetime | None = None) -> str:
    now = from_time or datetime.now()
    trigger = job.get("trigger") or "once"
    if trigger == "once":
        t = _parse(job.get("run_at") or "")
        if t and t > now:
            return t.strftime("%Y-%m-%d %H:%M:%S")
        return ""
    if trigger == "daily":
        hhmm = job.get("daily_time") or "09:00"
        try:
            h, m = [int(x) for x in hhmm.split(":")[:2]]
        except ValueError:
            h, m = 9, 0
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.strftime("%Y-%m-%d %H:%M:%S")
    minutes = int(job.get("interval_min") or 60)
    return (now + timedelta(minutes=max(1, minutes))).strftime("%Y-%m-%d %H:%M:%S")


def job_failed(report) -> bool:
    if getattr(report, "error", ""):
        return True
    return bool((report.summary or {}).get("FAIL"))


def should_retry(job: dict, report, attempt: int) -> bool:
    if attempt >= int(job.get("retry_max") or 0):
        return False
    reasons = job.get("retry_on") or ["FAIL", "NO_DEVICE", "LOCKED"]
    err = getattr(report, "error", "") or ""
    if err and err in reasons:
        return True
    if (report.summary or {}).get("FAIL") and "FAIL" in reasons:
        return True
    return False


def list_jobs() -> list[dict]:
    jobs = read_state().get("jobs") or []
    jobs.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return jobs


def get_job(job_id: str) -> dict | None:
    return next((j for j in list_jobs() if j["id"] == job_id), None)


def upsert_job(job: dict) -> dict:
    def mut(data):
        rows = data["jobs"]
        for i, old in enumerate(rows):
            if old["id"] == job["id"]:
                rows[i] = job
                return
        rows.append(job)

    update_state(mut)
    return job


def delete_job(job_id: str) -> bool:
    found = {"ok": False}

    def mut(data):
        before = len(data["jobs"])
        data["jobs"] = [j for j in data["jobs"] if j["id"] != job_id]
        found["ok"] = len(data["jobs"]) < before

    update_state(mut)
    return found["ok"]


def _append_history(job: dict, item: dict) -> None:
    hist = job.setdefault("history", [])
    hist.insert(0, item)
    job["history"] = hist[:30]


def execute_job(job_id: str, reason: str = "manual") -> dict:
    job = get_job(job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    if job.get("terminal_id", "local") != "local":
        job["status"] = "blocked"
        job["last_detail"] = "只有本机终端能下发执行"
        job["updated_at"] = now_iso()
        upsert_job(job)
        return {"ok": False, "error": job["last_detail"]}
    if BUSY["job_id"]:
        return {"ok": False, "error": "已有任务在跑", "busy": BUSY["job_id"]}

    BUSY["job_id"] = job_id
    BUSY["terminal_id"] = job.get("terminal_id") or "local"
    job["status"] = "running"
    job["updated_at"] = now_iso()
    upsert_job(job)

    attempt = 0
    last_report = None
    try:
        while True:
            attempt += 1
            last_report = run_suite(
                suite=job.get("suite") or "smoke",
                serial=job.get("device_serial") or None,
                only=job.get("cases") or None,
            )
            failed = job_failed(last_report)
            _append_history(
                job,
                {
                    "at": now_iso(),
                    "reason": reason,
                    "attempt": attempt,
                    "run_id": last_report.run_id,
                    "error": last_report.error,
                    "summary": last_report.summary,
                    "failed": failed,
                },
            )
            if not failed or not should_retry(job, last_report, attempt):
                break
            delay = int(job.get("retry_delay_sec") or 30)
            job["status"] = "retrying"
            job["last_detail"] = f"第 {attempt} 次失败，{delay}s 后重试"
            job["updated_at"] = now_iso()
            upsert_job(job)
            time.sleep(max(1, delay))

        job["last_run_id"] = last_report.run_id
        job["last_error"] = last_report.error
        job["last_summary"] = last_report.summary
        job["status"] = "failed" if job_failed(last_report) else "success"
        job["last_detail"] = last_report.error or ("有失败" if job_failed(last_report) else "通过")
        job["attempts"] = attempt
        if job.get("trigger") in ("daily", "interval") and job.get("enabled"):
            job["next_run_at"] = next_run_at(job)
        elif job.get("trigger") == "once":
            job["next_run_at"] = ""
            job["enabled"] = False
        job["updated_at"] = now_iso()
        upsert_job(job)
        return {"ok": True, "job": job, "run_id": last_report.run_id}
    except Exception as e:
        job["status"] = "failed"
        job["last_detail"] = str(e)
        job["updated_at"] = now_iso()
        upsert_job(job)
        return {"ok": False, "error": str(e)}
    finally:
        BUSY["job_id"] = ""
        BUSY["terminal_id"] = ""


def dispatch_async(job_id: str, reason: str = "manual") -> dict:
    if BUSY["job_id"]:
        return {"ok": False, "error": "已有任务在跑", "busy": BUSY["job_id"]}
    threading.Thread(target=execute_job, args=(job_id, reason), daemon=True).start()
    return {"ok": True, "accepted": True, "job_id": job_id}


def tick() -> None:
    now = datetime.now()
    if BUSY["job_id"]:
        return
    for job in list_jobs():
        if not job.get("enabled"):
            continue
        if job.get("status") == "running":
            continue
        nxt = _parse(job.get("next_run_at") or "")
        if nxt and nxt <= now:
            dispatch_async(job["id"], reason="schedule")
            return


def _loop():
    while True:
        try:
            tick()
        except Exception:
            pass
        time.sleep(15)


def start_scheduler() -> None:
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_loop, daemon=True).start()
