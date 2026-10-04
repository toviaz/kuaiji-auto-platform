from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.assertlib import Checks
from app.auth import hash_password
from app.catalog import get_case, list_cases
from app.models import CaseResult, RunReport, now_iso
from app.report import write_all


def test_password_hash():
    salt, digest = hash_password("secret")
    _, again = hash_password("secret", salt)
    _, other = hash_password("nope", salt)
    assert digest == again and digest != other


def test_catalog_has_twelve():
    cases = list_cases()
    assert len(cases) == 12
    assert get_case("KJ-03")["mode"] == "AUTO"
    assert get_case("KJ-10")["mode"] == "MANUAL"
    assert get_case("KJ-06")["asserts"]


def test_soft_assert_and_finalize():
    r = CaseResult(cid="KJ-T1", title="断言样例")
    chk = Checks(r)
    chk.equals("计时器", "00:03", "00:03")
    chk.contains("列表有文件", "KJ06A 00:03", "KJ06A")
    chk.truthy("分享面板", False, "未出现分享")
    r.finalize()
    assert r.status == "FAIL"
    assert len(r.assertions) == 3
    assert r.assertions[0].passed and r.assertions[1].passed
    assert not r.assertions[2].passed


def test_skip_keeps_status():
    r = CaseResult(cid="KJ-T2", title="跳过", status="SKIP", detail="已授权")
    chk = Checks(r)
    chk.truthy("不该改状态", True)
    r.finalize()
    assert r.status == "SKIP"


def test_write_reports(tmp_path: Path | None = None):
    out = Path(tmp_path) if tmp_path else ROOT / "data" / "runs" / "_selftest"
    out.mkdir(parents=True, exist_ok=True)
    pass_case = CaseResult(cid="KJ-03", title="列表点录音", started_at=now_iso())
    chk = Checks(pass_case)
    chk.contains("进入录音页", "RecordingActivity 00:02 结束", "结束")
    chk.ge("计时大于0", 2, 1)
    pass_case.finalize()
    fail_case = CaseResult(cid="KJ-06", title="重命名", started_at=now_iso())
    Checks(fail_case).contains("列表显示新文件名", "新录音 00:02", "KJ06A")
    fail_case.finalize()
    skip_case = CaseResult(cid="KJ-01", title="授权窗", status="SKIP", detail="已授权")
    man_case = CaseResult(cid="KJ-12", title="卸载重装", status="MANUAL", detail="会卸掉听记")
    report = RunReport(
        run_id=out.name,
        suite="smoke",
        serial="SAMPLE",
        aios="master_userdebug_sample",
        apk="1.1.4_sample",
        locked=False,
        started_at=now_iso(),
        ended_at=now_iso(),
        results=[pass_case, fail_case, skip_case, man_case],
    )
    paths = write_all(report, out)
    data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    assert data["summary"]["PASS"] == 1
    assert data["summary"]["FAIL"] == 1
    assert data["summary"]["SKIP"] == 1
    assert data["summary"]["MANUAL"] == 1
    html = Path(paths["html"]).read_text(encoding="utf-8")
    assert "KJ-03" in html and "KJ-06" in html
    assert "列表显示新文件名" in html
    junit = Path(paths["junit"]).read_text(encoding="utf-8")
    assert "<failure" in junit and "<skipped" in junit
    print("reports", paths)
    return paths


if __name__ == "__main__":
    test_soft_assert_and_finalize()
    test_skip_keeps_status()
    test_write_reports()
    print("OK")
