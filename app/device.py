from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def sh(args, timeout=30):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    out = (p.stdout or b"").decode("utf-8", "replace").replace("\r", "")
    err = (p.stderr or b"").decode("utf-8", "replace").replace("\r", "")
    return p.returncode, out, err


def list_serials() -> list[str]:
    _, out, _ = sh(["adb", "devices"])
    rows = []
    for ln in out.splitlines()[1:]:
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == "device":
            rows.append(parts[0])
    return rows


class Device:
    def __init__(self, serial: str, rundir: Path, cfg: dict):
        self.s = serial
        self.rundir = rundir
        self.rundir.mkdir(parents=True, exist_ok=True)
        self.cfg = cfg
        self._shot_i = 0
        self.shots: list[str] = []

    def adb(self, *args, timeout=40):
        return sh(["adb", "-s", self.s, *args], timeout=timeout)

    def shell(self, *args, timeout=40):
        code, out, err = self.adb("shell", *args, timeout=timeout)
        return code, out.strip(), err

    def is_locked(self) -> bool:
        _, out, _ = self.shell("dumpsys", "window", timeout=15)
        return "mDreamingLockscreen=true" in out or "isStatusBarKeyguard=true" in out

    def wake(self):
        self.shell("input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.4)
        if not self.is_locked():
            return
        self.shell("wm", "dismiss-keyguard")
        time.sleep(0.3)

    def home(self):
        self.shell("input", "keyevent", "KEYCODE_HOME")
        time.sleep(0.6)

    def back(self, n=1):
        for _ in range(n):
            self.shell("input", "keyevent", "KEYCODE_BACK")
            time.sleep(0.4)

    def tap(self, x, y):
        self.shell("input", "tap", str(int(x)), str(int(y)))
        time.sleep(0.5)

    def long_press(self, x, y, ms=900):
        self.shell("input", "swipe", str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(ms))
        time.sleep(0.5)

    def text(self, s):
        self.shell("input", "text", s.replace(" ", "%s"))
        time.sleep(0.3)

    def ime_ascii(self, s: str):
        n, b = self.find(rid="textInput")
        if b:
            self.tap(b[0], b[1])
            time.sleep(0.2)
        self.shell("input", "keyevent", "KEYCODE_MOVE_END")
        for _ in range(16):
            self.shell("input", "keyevent", "KEYCODE_DEL")
        self.text(s if all(ord(c) < 128 for c in s) else self.cfg.get("rename_to", "KJ06A"))
        time.sleep(0.3)

    def start_app(self):
        self.shell("am", "start", "-S", "-n", self.cfg["main_activity"])
        time.sleep(1.8)
        if self.exists("通话录音", "通话自动录音") and not self.exists("开始录音"):
            self.back(2)
            time.sleep(0.4)

    def force_stop(self):
        self.shell("am", "force-stop", self.cfg["package"])
        self.shell("am", "force-stop", "com.stepos.callsetting")
        time.sleep(0.4)

    def ensure_list(self):
        if self.exists("取消") and self.exists("保存", "重命名"):
            self.click_text("取消")
            time.sleep(0.3)
        act = self.activity()
        if "SettingActivity" in act or "RecordingActivity" in act:
            self.back(2)
            time.sleep(0.4)
        if not self.exists("开始录音", "快记"):
            self.force_stop()
            self.start_app()
            time.sleep(0.6)

    def dump(self) -> ET.Element | None:
        remote = "/sdcard/_uidump.xml"
        local = self.rundir / "uidump.xml"
        self.shell("rm", "-f", remote)
        code, _, _ = self.shell("uiautomator", "dump", remote, timeout=12)
        if code != 0:
            return None
        code, _, _ = self.adb("pull", remote, str(local), timeout=8)
        if code != 0:
            return None
        try:
            return ET.parse(local).getroot()
        except Exception:
            return None

    def nodes(self, root=None):
        root = root or self.dump()
        if root is None:
            return []
        return list(root.iter("node"))

    def bounds(self, node):
        m = re.search(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.attrib.get("bounds") or "")
        if not m:
            return None
        l, t, r, b = map(int, m.groups())
        return (l + r) // 2, (t + b) // 2, l, t, r, b

    def find(self, *texts, desc=None, rid=None, contains=True):
        for n in self.nodes():
            tx = n.attrib.get("text") or ""
            ds = n.attrib.get("content-desc") or ""
            ri = n.attrib.get("resource-id") or ""
            if texts:
                ok = False
                for t in texts:
                    if contains and (t in tx or t in ds):
                        ok = True
                    if not contains and (tx == t or ds == t):
                        ok = True
                if not ok:
                    continue
            if desc and desc not in ds:
                continue
            if rid and rid not in ri:
                continue
            b = self.bounds(n)
            if b:
                return n, b
        return None, None

    def click_text(self, *texts, retries=2) -> bool:
        for _ in range(retries):
            n, b = self.find(*texts)
            if b:
                self.tap(b[0], b[1])
                return True
            time.sleep(0.3)
        return False

    def tap_record(self) -> bool:
        n, b = self.find(desc="开始录音")
        if not b:
            n, b = self.find(rid="btn_rec")
        if b:
            self.tap(b[0], b[1])
            return True
        x, y = self.cfg.get("coords", {}).get("record_fallback", [599, 2418])
        self.tap(x, y)
        return True

    def tap_record_pause(self) -> bool:
        x, y = self.cfg.get("coords", {}).get("pause", [420, 2420])
        self.tap(x, y)
        return True

    def tap_record_finish(self) -> bool:
        x, y = self.cfg.get("coords", {}).get("finish", [750, 2420])
        self.tap(x, y)
        return True

    def exists(self, *texts) -> bool:
        n, b = self.find(*texts)
        return b is not None

    def ocr(self, tag="shot") -> str:
        self._shot_i += 1
        png = self.rundir / f"{self._shot_i:02d}_{tag}.png"
        self.shell("screencap", "-p", "/sdcard/_shot.png")
        self.adb("pull", "/sdcard/_shot.png", str(png))
        self.shell("rm", "-f", "/sdcard/_shot.png")
        self.shots.append(png.name)
        ocr_bin = Path(self.cfg.get("ocr_bin", ""))
        if ocr_bin.exists():
            _, out, _ = sh([str(ocr_bin), str(png)], timeout=20)
            (self.rundir / f"{self._shot_i:02d}_{tag}.txt").write_text(out, encoding="utf-8")
            return out
        return ""

    def activity(self) -> str:
        _, out, _ = self.shell("dumpsys", "activity", "activities")
        m = re.search(r"topResumedActivity=ActivityRecord\{[^ ]+ [^ ]+ ([^\s]+) t\d+", out)
        return m.group(1) if m else ""

    def aios_version(self) -> str:
        _, out, _ = self.shell("getprop", "ro.build.aios_version")
        return out

    def apk_version(self) -> str:
        _, out, _ = self.shell("dumpsys", "package", self.cfg["package"])
        m = re.search(r"versionName=(\S+)", out)
        return m.group(1) if m else ""
