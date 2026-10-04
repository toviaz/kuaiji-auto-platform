from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from ..auth import (
    COOKIE,
    approve_user,
    authorize_url,
    create_session,
    drop_session,
    list_users,
    login_feishu_code,
    login_feishu_local_token,
    login_local,
    public_user,
    register_local,
    set_user_role,
    user_by_session,
)
from ..catalog import get_case, list_cases
from ..config import load_config
from ..device import list_serials
from ..runner import run_suite

STATIC = Path(__file__).parent / "static"
RUNNING: dict = {"busy": False, "run_id": ""}


def _runs_root() -> Path:
    return Path(load_config()["output_dir"])


def _pass_rate(summary: dict) -> float:
    judged = (summary.get("PASS") or 0) + (summary.get("FAIL") or 0)
    if not judged:
        return 0.0
    return round(100.0 * (summary.get("PASS") or 0) / judged, 1)


def _list_runs() -> list[dict]:
    root = _runs_root()
    if not root.exists():
        return []
    items = []
    for d in sorted(root.iterdir(), reverse=True):
        jp = d / "report.json"
        if not jp.exists():
            continue
        data = json.loads(jp.read_text(encoding="utf-8"))
        items.append(
            {
                "run_id": data.get("run_id", d.name),
                "suite": data.get("suite", ""),
                "started_at": data.get("started_at", ""),
                "ended_at": data.get("ended_at", ""),
                "serial": data.get("serial", ""),
                "aios": data.get("aios", ""),
                "apk": data.get("apk", ""),
                "summary": data.get("summary", {}),
                "error": data.get("error", ""),
                "total": len(data.get("results") or []),
                "pass_rate": _pass_rate(data.get("summary") or {}),
            }
        )
    items.sort(key=lambda x: x.get("started_at") or x.get("run_id") or "", reverse=True)
    return items


app = FastAPI(title="快记自动化测试平台", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

PUBLIC_EXACT = {
    "/login",
    "/register",
    "/login/feishu/callback",
    "/api/auth/me",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/feishu/local",
    "/api/auth/feishu/authorize-url",
}
PUBLIC_PREFIX = ("/static", "/auth/")


class AuthGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_EXACT or any(path.startswith(p) for p in PUBLIC_PREFIX):
            return await call_next(request)
        user = user_by_session(request.cookies.get(COOKIE))
        if user:
            request.state.user = user
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        nxt = path if path != "/" else "/"
        return RedirectResponse("/login?next=" + nxt, status_code=302)


app.add_middleware(AuthGate)


def _page(name: str):
    return FileResponse(STATIC / name, media_type="text/html")


def _req_user(request: Request) -> dict | None:
    return getattr(request.state, "user", None) or user_by_session(request.cookies.get(COOKIE))


def _require_admin(request: Request) -> dict:
    user = _req_user(request)
    if not user or not user.get("is_admin"):
        raise HTTPException(403, "只有管理员可以操作")
    return user


@app.get("/login", response_class=HTMLResponse)
def page_login():
    return _page("login.html")


@app.get("/register", response_class=HTMLResponse)
def page_register():
    return _page("register.html")


@app.get("/account", response_class=HTMLResponse)
def page_account():
    return _page("account.html")


@app.get("/users", response_class=HTMLResponse)
def page_users(request: Request):
    user = _req_user(request)
    if not user or not user.get("is_admin"):
        return RedirectResponse("/", status_code=302)
    return _page("users.html")


@app.get("/", response_class=HTMLResponse)
def page_home():
    return _page("overview.html")


@app.get("/cases", response_class=HTMLResponse)
def page_cases():
    return _page("cases.html")


@app.get("/cases/{cid}", response_class=HTMLResponse)
def page_case(cid: str):
    if not get_case(cid):
        raise HTTPException(404, "case not found")
    return _page("case.html")


@app.get("/results", response_class=HTMLResponse)
def page_results():
    return _page("results.html")


@app.get("/report", response_class=HTMLResponse)
def page_report():
    return _page("report.html")


@app.get("/report/{run_id}", response_class=HTMLResponse)
def page_report_id(run_id: str):
    return _page("report.html")


class LocalAuth(BaseModel):
    username: str
    password: str
    name: str = ""


def _set_login(resp, user: dict):
    sid = create_session(user)
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", path="/")
    return resp


@app.get("/api/auth/me")
def api_me(request: Request):
    return {"user": user_by_session(request.cookies.get(COOKIE))}


@app.post("/api/auth/register")
def api_register(payload: LocalAuth):
    try:
        user = register_local(payload.username, payload.password, payload.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"ok": True, "user": public_user(user)})
    return _set_login(resp, user)


@app.post("/api/auth/login")
def api_login(payload: LocalAuth):
    try:
        user = login_local(payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"ok": True, "user": public_user(user)})
    return _set_login(resp, user)


@app.post("/api/auth/logout")
def api_logout(request: Request):
    drop_session(request.cookies.get(COOKIE) or "")
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.get("/auth/feishu")
def auth_feishu():
    return RedirectResponse(authorize_url(), status_code=302)


def _feishu_callback(code: str, state: str, next: str):
    try:
        user = login_feishu_code(code, state)
    except ValueError as e:
        return RedirectResponse("/login?err=" + str(e), status_code=302)
    resp = RedirectResponse(next or "/", status_code=302)
    return _set_login(resp, user)


@app.get("/auth/feishu/callback")
def auth_feishu_callback(code: str = "", state: str = "", next: str = "/"):
    return _feishu_callback(code, state, next)


@app.get("/login/feishu/callback")
def login_feishu_callback(code: str = "", state: str = "", next: str = "/"):
    return _feishu_callback(code, state, next)


@app.get("/api/auth/feishu/authorize-url")
def api_feishu_authorize_url():
    return {"url": authorize_url()}


@app.get("/api/users")
def api_users(request: Request):
    _require_admin(request)
    return {"users": list_users()}


class RoleReq(BaseModel):
    role: str


@app.post("/api/users/{user_id}/role")
def api_set_role(user_id: str, payload: RoleReq, request: Request):
    _require_admin(request)
    try:
        return {"ok": True, "user": set_user_role(user_id, payload.role)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/users/{user_id}/approve")
def api_approve(user_id: str, request: Request):
    _require_admin(request)
    try:
        return {"ok": True, "user": approve_user(user_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/auth/feishu/local")
def api_feishu_local():
    try:
        user = login_feishu_local_token()
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"ok": True, "user": public_user(user)})
    return _set_login(resp, user)


@app.get("/api/devices")
def api_devices():
    return {"devices": list_serials()}


@app.get("/api/suite")
def api_suite():
    cfg = load_config()
    smoke = (cfg.get("suites") or {}).get("smoke") or {}
    cases = list_cases()
    return {
        "suite": "smoke",
        "name": smoke.get("name", "快记每日点检"),
        "source": cfg.get("source", ""),
        "cases": cases,
        "total": len(cases),
        "auto": sum(1 for c in cases if c["mode"] == "AUTO"),
        "manual": sum(1 for c in cases if c["mode"] == "MANUAL"),
    }


def _case_history(cid: str, limit: int = 8) -> list[dict]:
    rows = []
    for run in _list_runs():
        jp = _runs_root() / run["run_id"] / "report.json"
        if not jp.exists():
            continue
        data = json.loads(jp.read_text(encoding="utf-8"))
        hit = next((x for x in data.get("results") or [] if x.get("cid") == cid), None)
        if not hit:
            continue
        rows.append(
            {
                "run_id": run["run_id"],
                "started_at": run.get("started_at", ""),
                "status": hit.get("status", ""),
                "detail": hit.get("detail", ""),
            }
        )
        if len(rows) >= limit:
            break
    return rows


@app.get("/api/cases")
def api_cases():
    latest = (_list_runs() or [None])[0]
    latest_map = {}
    if latest:
        jp = _runs_root() / latest["run_id"] / "report.json"
        if jp.exists():
            data = json.loads(jp.read_text(encoding="utf-8"))
            latest_map = {x["cid"]: x for x in data.get("results") or []}
    cases = []
    for c in list_cases():
        last = latest_map.get(c["cid"])
        item = dict(c)
        item["last_status"] = last.get("status") if last else ""
        item["last_run"] = latest["run_id"] if last else ""
        item["last_detail"] = last.get("detail") if last else ""
        cases.append(item)
    return {"cases": cases}


@app.get("/api/cases/{cid}")
def api_case(cid: str):
    c = get_case(cid)
    if not c:
        raise HTTPException(404, "case not found")
    c["history"] = _case_history(cid)
    return c


@app.get("/api/overview")
def api_overview():
    cfg = load_config()
    cases = list_cases()
    runs = _list_runs()
    latest = runs[0] if runs else None
    summary = (latest or {}).get("summary") or {}
    return {
        "name": cfg.get("app_name", "快记点检"),
        "suite": "smoke",
        "source": cfg.get("source", ""),
        "cases_total": len(cases),
        "auto": sum(1 for c in cases if c["mode"] == "AUTO"),
        "manual": sum(1 for c in cases if c["mode"] == "MANUAL"),
        "modules": sorted({c["module"] for c in cases}),
        "runs_total": len(runs),
        "latest": latest,
        "pass_rate": _pass_rate(summary) if latest else 0,
        "recent": runs[:8],
    }


@app.get("/api/runs")
def api_runs():
    return {"runs": _list_runs(), "busy": RUNNING["busy"], "current": RUNNING["run_id"]}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    jp = _runs_root() / run_id / "report.json"
    if not jp.exists():
        raise HTTPException(404, "run not found")
    return JSONResponse(json.loads(jp.read_text(encoding="utf-8")))


@app.get("/runs/{run_id}/{name}")
def run_file(run_id: str, name: str):
    p = (_runs_root() / run_id / name).resolve()
    root = (_runs_root() / run_id).resolve()
    if not str(p).startswith(str(root)):
        raise HTTPException(400, "bad path")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "file not found")
    media = "text/html" if name.endswith(".html") else None
    return FileResponse(p, media_type=media)


class RunReq(BaseModel):
    suite: str = "smoke"
    serial: str | None = None
    only: list[str] | None = None


def _bg_run(suite: str, serial: str | None, only: list[str] | None):
    try:
        report = run_suite(suite=suite, serial=serial, only=only)
        RUNNING["run_id"] = report.run_id
    finally:
        RUNNING["busy"] = False


@app.post("/api/run")
def api_run_start(request: Request, payload: RunReq | None = None):
    _require_admin(request)
    if RUNNING["busy"]:
        raise HTTPException(409, "already running")
    payload = payload or RunReq()
    RUNNING["busy"] = True
    RUNNING["run_id"] = ""
    t = threading.Thread(
        target=_bg_run,
        kwargs={
            "suite": payload.suite or "smoke",
            "serial": payload.serial,
            "only": payload.only,
        },
        daemon=True,
    )
    t.start()
    return {"ok": True, "busy": True}


def serve(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")
