from __future__ import annotations

import argparse
import json
import sys

from .device import list_serials
from .runner import run_suite


def main(argv=None):
    p = argparse.ArgumentParser(description="快记自动化测试平台")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="跑套件")
    r.add_argument("--suite", default="smoke")
    r.add_argument("--serial")
    r.add_argument("--only", nargs="*", help="只跑这些编号，如 KJ-03 KJ-04")

    sub.add_parser("devices", help="列出在线设备")

    w = sub.add_parser("web", help="打开 Web 控制台")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8765)

    args = p.parse_args(argv)
    if args.cmd == "devices":
        rows = list_serials()
        print("\n".join(rows) if rows else "NO_DEVICE")
        return 0 if rows else 2
    if args.cmd == "web":
        from .web.server import serve

        print(f"控制台 http://{args.host}:{args.port}")
        serve(host=args.host, port=args.port)
        return 0
    report = run_suite(suite=args.suite, serial=args.serial, only=args.only)
    if report.error == "NO_DEVICE":
        print("NO_DEVICE")
        return 2
    if report.error == "LOCKED":
        print("LOCKED 请先解锁")
        return 3
    print(json.dumps(report.summary, ensure_ascii=False))
    return 1 if report.summary.get("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
