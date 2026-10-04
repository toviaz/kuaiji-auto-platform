from __future__ import annotations

import html
import json
from pathlib import Path
from xml.sax.saxutils import escape

from .models import RunReport


def write_json(report: RunReport, rundir: Path) -> Path:
    p = rundir / "report.json"
    p.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def write_junit(report: RunReport, rundir: Path) -> Path:
    rows = []
    for c in report.results:
        name = escape(f"{c.cid} {c.title}")
        if c.status == "PASS":
            rows.append(f'<testcase classname="kuaiji.smoke" name="{name}" time="{c.elapsed_ms/1000:.3f}"/>')
        elif c.status in ("SKIP", "MANUAL"):
            rows.append(
                f'<testcase classname="kuaiji.smoke" name="{name}" time="{c.elapsed_ms/1000:.3f}">'
                f'<skipped message="{escape(c.detail)}"/></testcase>'
            )
        else:
            rows.append(
                f'<testcase classname="kuaiji.smoke" name="{name}" time="{c.elapsed_ms/1000:.3f}">'
                f'<failure message="{escape(c.detail)}">{escape(c.detail)}</failure></testcase>'
            )
    s = report.summary
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="kuaiji-smoke" tests="{len(report.results)}" '
        f'failures="{s["FAIL"]}" skipped="{s["SKIP"]+s["MANUAL"]}" time="0">\n'
        + "\n".join(rows)
        + "\n</testsuite>\n"
    )
    p = rundir / "junit.xml"
    p.write_text(xml, encoding="utf-8")
    return p


def write_html(report: RunReport, rundir: Path) -> Path:
    s = report.summary
    rows = []
    for c in report.results:
        color = {
            "PASS": "#15803d",
            "FAIL": "#b91c1c",
            "SKIP": "#a16207",
            "MANUAL": "#1d4ed8",
            "BLOCK": "#6b7280",
        }.get(c.status, "#111")
        asserts = "".join(
            f"<tr><td>{'✓' if a.passed else '✗'}</td><td>{html.escape(a.name)}</td>"
            f"<td>{html.escape(a.expected)}</td><td>{html.escape(a.actual)}</td></tr>"
            for a in c.assertions
        ) or "<tr><td colspan=4>无断言（SKIP/MANUAL）</td></tr>"
        shots = " ".join(
            f'<a href="{html.escape(x)}" target="_blank">{html.escape(x)}</a>' for x in c.screenshots
        )
        rows.append(
            f"""<section class="case">
<h3 style="color:{color}">{html.escape(c.cid)} {c.status} · {html.escape(c.title)}</h3>
<p>{html.escape(c.detail)}　耗时 {c.elapsed_ms}ms</p>
<p class="shots">{shots}</p>
<table><thead><tr><th></th><th>断言</th><th>期望</th><th>实际</th></tr></thead>
<tbody>{asserts}</tbody></table>
</section>"""
        )
    body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>点检报告 {html.escape(report.run_id)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:24px;color:#111;background:#f8fafc}}
.bar span{{display:inline-block;margin-right:12px;padding:4px 10px;border-radius:8px;background:#fff;border:1px solid #e5e7eb}}
.case{{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:16px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td,th{{border-bottom:1px solid #f1f5f9;padding:6px 8px;text-align:left;vertical-align:top}}
.meta{{color:#64748b;font-size:13px}}
</style></head><body>
<h1>快记点检报告</h1>
<p class="meta">run={html.escape(report.run_id)}　设备={html.escape(report.serial)}　
固件={html.escape(report.aios)}　APK={html.escape(report.apk)}</p>
<p class="bar">
<span>PASS {s['PASS']}</span><span>FAIL {s['FAIL']}</span>
<span>SKIP {s['SKIP']}</span><span>MANUAL {s['MANUAL']}</span>
</p>
{''.join(rows)}
</body></html>"""
    p = rundir / "report.html"
    p.write_text(body, encoding="utf-8")
    return p


def write_all(report: RunReport, rundir: Path) -> dict[str, str]:
    return {
        "json": str(write_json(report, rundir)),
        "html": str(write_html(report, rundir)),
        "junit": str(write_junit(report, rundir)),
    }
