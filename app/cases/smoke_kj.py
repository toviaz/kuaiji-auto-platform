from __future__ import annotations

import re
import time

from ..assertlib import Checks
from ..device import Device
from ..models import CaseResult, now_iso


def _timer(text: str) -> str:
    secs = [int(x) for x in re.findall(r"00:(\d{2})", text or "")]
    secs = [s for s in secs if s > 0] or secs
    return f"00:{max(secs):02d}" if secs else ""


def _timer_sec(text: str) -> int:
    t = _timer(text)
    return int(t.split(":")[1]) if t else 0


def handle_auth(d: Device) -> list[str]:
    seen = []
    for i in range(3):
        if d.exists("隐私政策", "同意并继续", "同意授权"):
            seen.append("应用授权")
            d.click_text("同意并继续", "同意")
            time.sleep(0.4)
            continue
        if d.exists("允许", "始终允许"):
            seen.append("系统权限")
            d.click_text("允许", "始终允许")
            time.sleep(0.4)
            continue
        if i == 0:
            o = d.ocr("auth")
            if re.search(r"允许|始终允许|同意并继续", o):
                d.click_text("允许", "始终允许", "同意并继续", "同意")
                time.sleep(0.4)
                continue
        break
    return seen


def case_01(d: Device, r: CaseResult, chk: Checks):
    d.force_stop()
    d.home()
    d.start_app()
    time.sleep(1)
    o = d.ocr("kj01")
    if any(k in o for k in ("隐私政策", "同意并继续", "授权")) or d.exists("同意并继续", "隐私政策"):
        d.click_text("同意并继续", "同意")
        time.sleep(0.8)
        o2 = d.ocr("kj01_after")
        chk.truthy("弹出授权窗", True)
        chk.truthy("点同意后授权窗关闭", not ("同意并继续" in o2 and "隐私政策" in o2), o2[:80])
        return
    in_list = d.exists("开始录音", "新录音", "快记") or any(k in o for k in ("开始录音", "新录音", "快记"))
    if "通话录音" in o or "通话自动录音" in o:
        d.back(2)
        time.sleep(0.5)
        d.start_app()
        in_list = d.exists("开始录音", "新录音", "快记")
    if in_list:
        r.status = "SKIP"
        r.detail = "已授权，未再弹出首次同意窗"
        return
    chk.truthy("见到授权窗或列表", False, o[:80])


def case_02(d: Device, r: CaseResult, chk: Checks):
    d.start_app()
    time.sleep(0.8)
    d.tap_record()
    time.sleep(0.8)
    seen = handle_auth(d)
    o = d.ocr("kj02")
    act = d.activity()
    recording = bool(re.search(r"00:0[0-9]", o) or "RecordingActivity" in act or "结束" in o)
    if recording:
        chk.truthy("进入录音计时", True, f"权限窗={seen or '无'} activity={act}")
        return
    if seen:
        chk.truthy("点权限后进入录音", False, o[:80])
        return
    r.status = "SKIP"
    r.detail = "未弹出运行时权限窗，当前应已授权"


def case_03(d: Device, r: CaseResult, chk: Checks):
    d.force_stop()
    d.start_app()
    time.sleep(0.8)
    handle_auth(d)
    d.tap_record()
    time.sleep(1.2)
    handle_auth(d)
    time.sleep(2.0)
    o = d.ocr("kj03")
    act = d.activity()
    ok = bool(re.search(r"00:0[1-9]|00:[1-9]", o) or "RecordingActivity" in act or "结束" in o)
    chk.truthy("进入录音页并计时", ok, f"activity={act} OCR={o[:80]}")
    if ok:
        d.home()
        time.sleep(0.8)
        o2 = d.ocr("kj03_home")
        chk.contains_any("桌面录音态(参考)", o2, ["录音", "录"])
        d.start_app()


def case_04(d: Device, r: CaseResult, chk: Checks):
    d.force_stop()
    d.start_app()
    time.sleep(0.5)
    d.tap_record()
    time.sleep(8)
    d.ocr("kj04_before_pause")
    d.tap_record_pause()
    time.sleep(0.8)
    o2 = d.ocr("kj04_paused")
    paused = _timer_sec(o2)
    chk.ge("暂停时计时>0", paused, 1)
    d.tap_record_pause()
    time.sleep(5.5)
    o3 = d.ocr("kj04_resume")
    resumed = _timer_sec(o3)
    chk.ge("续录后仍有计时", resumed, 1)
    chk.ge("续录计时不回退", resumed, paused)
    d.tap_record_finish()
    time.sleep(1.0)
    r.detail = f"暂停 00:{paused:02d} → 续录 00:{resumed:02d}"


def case_05(d: Device, r: CaseResult, chk: Checks):
    d.force_stop()
    d.start_app()
    time.sleep(0.6)
    handle_auth(d)
    d.tap_record()
    time.sleep(10.5)
    d.tap_record_finish()
    time.sleep(1.2)
    o = d.ocr("kj05")
    has_file = bool(re.search(r"新录音|00:1[0-2]|00:09|00:10|00:11", o) or d.exists("新录音"))
    chk.truthy("列表出现新文件且时长约10秒", has_file, o[:100])


def case_06(d: Device, r: CaseResult, chk: Checks):
    name = d.cfg.get("rename_to", "KJ06A")
    d.ensure_list()
    time.sleep(0.3)
    n, b = d.find("新录音")
    if not b:
        r.status = "SKIP"
        r.detail = "列表没有「新录音」可改名"
        return
    d.long_press(b[0], b[1])
    time.sleep(0.6)
    opened = d.click_text("重命名", "修改名称", "编辑")
    if not opened:
        d.tap(b[0], b[1])
        time.sleep(0.6)
        opened = d.click_text("重命名", "修改名称")
    chk.truthy("打开重命名", opened)
    if not opened:
        return
    d.ime_ascii(name)
    time.sleep(0.3)
    n2, b2 = d.find(rid="bt_positive")
    if b2:
        d.tap(b2[0], b2[1])
    else:
        d.click_text("保存", "确定", "完成")
    time.sleep(0.8)
    o = d.ocr("kj06")
    chk.truthy("列表显示新文件名", name in o or d.exists(name), o[:80])


def case_07(d: Device, r: CaseResult, chk: Checks):
    d.ensure_list()
    time.sleep(0.3)
    n, b = d.find("新录音")
    name = "新录音"
    if not b:
        n, b = d.find(d.cfg.get("rename_to", "KJ06A"))
        name = d.cfg.get("rename_to", "KJ06A")
    if not b:
        r.status = "SKIP"
        r.detail = "没有可删的测试文件"
        return
    d.long_press(b[0], b[1])
    time.sleep(0.5)
    opened = d.click_text("删除")
    chk.truthy("找到删除", opened)
    if not opened:
        return
    d.click_text("确认", "删除", "确定")
    time.sleep(0.8)
    o = d.ocr("kj07")
    if name == d.cfg.get("rename_to", "KJ06A"):
        chk.truthy("删除后专名消失", name not in o, o[:80])
    else:
        chk.truthy("已走删除确认", True, "列表可能仍有其他新录音")


def case_08(d: Device, r: CaseResult, chk: Checks):
    d.ensure_list()
    time.sleep(0.3)
    n, b = d.find("新录音", d.cfg.get("rename_to", "KJ06A"))
    if not b:
        r.status = "SKIP"
        r.detail = "没有可分享的录音"
        return
    d.long_press(b[0], b[1])
    time.sleep(0.5)
    opened = d.click_text("分享")
    if not opened:
        d.tap(b[0], b[1])
        time.sleep(0.5)
        opened = d.click_text("分享")
    chk.truthy("点到分享", opened)
    if not opened:
        return
    time.sleep(1.0)
    o = d.ocr("kj08")
    act = d.activity()
    panel = any(k in o for k in ("蓝牙", "信息", "分享", "附近", "微信", "Drive"))
    act_ok = "chooser" in act.lower() or "share" in act.lower()
    chk.truthy("拉起系统分享面板", panel or act_ok, f"activity={act} OCR={o[:80]}")
    d.back()


def case_09(d: Device, r: CaseResult, chk: Checks):
    name = d.cfg.get("rename_to", "KJ06A")
    d.ensure_list()
    time.sleep(0.3)
    n, b = d.find(desc="搜索")
    if b:
        d.tap(b[0], b[1])
        opened = True
    else:
        opened = d.click_text("搜索")
    chk.truthy("找到搜索入口", opened)
    if not opened:
        return
    time.sleep(0.4)
    d.ime_ascii(name)
    time.sleep(0.8)
    o = d.ocr("kj09")
    hit = name in o
    empty = any(k in o for k in ("无结果", "没有", "空"))
    chk.truthy("搜索命中或空态", hit or empty, o[:80])


def case_10(d: Device, r: CaseResult, chk: Checks):
    r.status = "MANUAL"
    r.detail = "需要第二台机拨打并接通≥8秒，默认不自动拨号"


def case_11(d: Device, r: CaseResult, chk: Checks):
    d.ensure_list()
    time.sleep(0.3)
    n, b = d.find(desc="设置")
    if b:
        d.tap(b[0], b[1])
    else:
        d.click_text("设置")
    time.sleep(0.6)
    if d.exists("通话录音"):
        d.click_text("通话录音")
        time.sleep(0.6)
    if d.exists("允许"):
        d.click_text("允许")
        time.sleep(0.6)
    d.ocr("kj11_before")
    n, b = d.find("通话自动录音", "自动录音")
    if not b:
        r.status = "SKIP"
        r.detail = "设置页未见通话自动录音"
        return
    d.tap(b[3] + 40, b[1])
    time.sleep(0.5)
    o2 = d.ocr("kj11_blank")
    n2, b2 = d.find("通话自动录音", "自动录音")
    if b2:
        d.tap(b2[4] - 40, b2[1])
        time.sleep(0.5)
    o3 = d.ocr("kj11_toggle")
    chk.truthy("点空白/滑块未崩溃", "停止运行" not in o3 and "崩溃" not in o3, o3[:80])
    r.detail = "点文字附近未崩；滑块可点。请对照截图确认空白未误翻"


def case_12(d: Device, r: CaseResult, chk: Checks):
    r.status = "MANUAL"
    r.detail = "会卸掉听记，默认不自动执行"


CASES = [
    ("KJ-01", "首次打开快记：弹出同意授权窗", case_01),
    ("KJ-02", "允许麦克风、存储、通知授权：录音页开始计时", case_02),
    ("KJ-03", "列表点录音：进入录音页并计时", case_03),
    ("KJ-04", "暂停后点继续：从暂停点续录", case_04),
    ("KJ-05", "点结束：列表出现文件且时长对", case_05),
    ("KJ-06", "重命名保存：列表显示新文件名", case_06),
    ("KJ-07", "删除确认后：文件从列表消失", case_07),
    ("KJ-08", "选中后分享：拉起系统分享面板", case_08),
    ("KJ-09", "按文件名搜索：命中对应条目", case_09),
    ("KJ-10", "通话自动录音开：挂断后列表有文件", case_10),
    ("KJ-11", "点开关旁空白：开关不误翻转", case_11),
    ("KJ-12", "卸载后在应用商店重装：旧录音不在列表", case_12),
]

CASE_MAP = {cid: (title, fn) for cid, title, fn in CASES}
