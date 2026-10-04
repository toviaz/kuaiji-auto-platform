from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from .assertlib import Checks
from .cases import CASE_MAP
from .config import load_config
from .device import Device, list_serials
from .models import CaseResult, RunReport, now_iso
from .report import write_all


def run_suite(suite: str = "smoke", serial: str | None = None, only: list[str] | None = None) -> RunReport:
    cfg = load_config()
    serials = list_serials()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rundir = Path(cfg["output_dir"]) / ts
    rundir.mkdir(parents=True, exist_ok=True)

    if not serials:
        report = RunReport(
            run_id=ts,
            suite=suite,
            serial="",
            aios="",
            apk="",
            locked=False,
            started_at=now_iso(),
            source=cfg.get("source", ""),
            error="NO_DEVICE",
        )
        report.ended_at = now_iso()
        write_all(report, rundir)
        return report

    serial = serial or serials[0]
    d = Device(serial, rundir, cfg)
    locked = d.is_locked()
    report = RunReport(
        run_id=ts,
        suite=suite,
        serial=serial,
        aios=d.aios_version(),
        apk=d.apk_version(),
        locked=locked,
        started_at=now_iso(),
        source=cfg.get("source", ""),
    )
    if locked:
        report.error = "LOCKED"
        report.ended_at = now_iso()
        write_all(report, rundir)
        return report

    suite_cfg = cfg.get("suites", {}).get(suite, {})
    wanted = only or suite_cfg.get("cases") or list(CASE_MAP)
    d.wake()
    for cid in wanted:
        title, fn = CASE_MAP[cid]
        res = CaseResult(cid=cid, title=title, started_at=now_iso())
        chk = Checks(res)
        t0 = time.time()
        print(f"\n== {cid} {title} ==", flush=True)
        try:
            fn(d, res, chk)
            res.screenshots = list(d.shots)
            d.shots.clear()
            res.finalize()
        except Exception as e:
            res.status = "FAIL"
            res.detail = str(e)
        res.ended_at = now_iso()
        res.elapsed_ms = int((time.time() - t0) * 1000)
        print(f"{res.cid} {res.status} | {res.detail}", flush=True)
        for a in res.assertions:
            mark = "PASS" if a.passed else "FAIL"
            print(f"  [{mark}] {a.name} expected={a.expected} actual={a.actual[:60]}", flush=True)
        report.results.append(res)
        time.sleep(0.3)

    report.ended_at = now_iso()
    paths = write_all(report, rundir)
    print("\n==== SUMMARY ====", flush=True)
    print(report.summary, flush=True)
    print(f"html={paths['html']}", flush=True)
    print(f"json={paths['json']}", flush=True)
    print(f"junit={paths['junit']}", flush=True)
    return report
