"""写演示报告，给结果列表和报告页看。不碰真机。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.assertlib import Checks
from app.catalog import list_cases
from app.models import CaseResult, RunReport
from app.report import write_all


DEMOS = [
    {
        "run_id": "demo_20261004_114000",
        "serial": "ZYPZ261A01M6760010F",
        "aios": "master_userdebug_20261003_025629",
        "apk": "1.1.4_20260930_174706",
        "started_at": "2026-10-04 11:40:00",
        "ended_at": "2026-10-04 11:48:12",
        "rows": {
            "KJ-01": ("SKIP", "已授权，未再弹出首次同意窗", []),
            "KJ-02": ("PASS", "2 条断言通过", [("进入录音或已授权", True, "true", "true"), ("计时开始", True, ">= 1", "2")]),
            "KJ-03": ("PASS", "2 条断言通过", [("进入录音页", True, "包含 结束", "RecordingActivity 00:02 结束"), ("计时大于0", True, ">= 1", "2")]),
            "KJ-04": ("PASS", "2 条断言通过", [("暂停后计时停住", True, "true", "true"), ("继续后秒数不回零", True, "true", "true")]),
            "KJ-05": ("PASS", "2 条断言通过", [("列表出现新文件", True, "包含 新录音", "新录音 00:10"), ("时长与录音接近", True, ">= 8", "10")]),
            "KJ-06": ("FAIL", "列表显示 KJ06A 不满足", [("打开重命名", True, "true", "true"), ("列表显示 KJ06A", False, "包含 KJ06A", "新录音 00:10")]),
            "KJ-07": ("PASS", "2 条断言通过", [("弹出删除确认", True, "true", "true"), ("目标文件从列表消失", True, "true", "true")]),
            "KJ-08": ("PASS", "2 条断言通过", [("点到分享", True, "true", "true"), ("拉起系统分享面板", True, "true", "true")]),
            "KJ-09": ("PASS", "2 条断言通过", [("找到搜索入口", True, "true", "true"), ("搜索命中或空态", True, "true", "true")]),
            "KJ-10": ("MANUAL", "需要第二台机拨打并接通≥8秒", []),
            "KJ-11": ("PASS", "点文字附近未崩", [("点空白/滑块未崩溃", True, "true", "true")]),
            "KJ-12": ("MANUAL", "会卸掉听记，默认不自动执行", []),
        },
    },
    {
        "run_id": "demo_20261003_163200",
        "serial": "ZYPZ261A01M6870011U",
        "aios": "master_userdebug_20261003_025629",
        "apk": "1.1.4_20260930_174706",
        "started_at": "2026-10-03 16:32:00",
        "ended_at": "2026-10-03 16:39:40",
        "rows": {
            "KJ-01": ("SKIP", "已授权，未再弹出首次同意窗", []),
            "KJ-02": ("PASS", "2 条断言通过", [("进入录音或已授权", True, "true", "true"), ("计时开始", True, ">= 1", "3")]),
            "KJ-03": ("PASS", "2 条断言通过", [("进入录音页", True, "包含 结束", "00:03 结束"), ("计时大于0", True, ">= 1", "3")]),
            "KJ-04": ("PASS", "2 条断言通过", [("暂停后计时停住", True, "true", "true"), ("继续后秒数不回零", True, "true", "true")]),
            "KJ-05": ("PASS", "2 条断言通过", [("列表出现新文件", True, "包含 新录音", "新录音 00:11"), ("时长与录音接近", True, ">= 8", "11")]),
            "KJ-06": ("PASS", "2 条断言通过", [("打开重命名", True, "true", "true"), ("列表显示 KJ06A", True, "包含 KJ06A", "KJ06A 00:11")]),
            "KJ-07": ("PASS", "2 条断言通过", [("弹出删除确认", True, "true", "true"), ("目标文件从列表消失", True, "true", "true")]),
            "KJ-08": ("PASS", "2 条断言通过", [("点到分享", True, "true", "true"), ("拉起系统分享面板", True, "true", "true")]),
            "KJ-09": ("PASS", "2 条断言通过", [("找到搜索入口", True, "true", "true"), ("搜索命中或空态", True, "包含 KJ06A", "KJ06A 00:11")]),
            "KJ-10": ("MANUAL", "需要第二台机拨打并接通≥8秒", []),
            "KJ-11": ("PASS", "点文字附近未崩", [("点空白/滑块未崩溃", True, "true", "true")]),
            "KJ-12": ("MANUAL", "会卸掉听记，默认不自动执行", []),
        },
    },
]


def build(demo: dict) -> Path:
    out = ROOT / "data" / "runs" / demo["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for meta in list_cases():
        cid = meta["cid"]
        status, detail, asserts = demo["rows"][cid]
        r = CaseResult(
            cid=cid,
            title=meta["title"],
            status=status,
            detail=detail,
            started_at=demo["started_at"],
            ended_at=demo["ended_at"],
            elapsed_ms=900,
        )
        chk = Checks(r)
        for name, ok, exp, act in asserts:
            chk._add(name, ok, exp, act)
        if status not in ("SKIP", "MANUAL"):
            r.finalize()
            r.detail = detail
        results.append(r)
    report = RunReport(
        run_id=demo["run_id"],
        suite="smoke",
        serial=demo["serial"],
        aios=demo["aios"],
        apk=demo["apk"],
        locked=False,
        started_at=demo["started_at"],
        ended_at=demo["ended_at"],
        source="demo",
        results=results,
    )
    write_all(report, out)
    return out


def main():
    for demo in DEMOS:
        print(build(demo))


if __name__ == "__main__":
    main()
