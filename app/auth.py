from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from .config import ROOT

AUTH_DIR = ROOT / "data" / "platform"
USERS = AUTH_DIR / "users.json"
SESSIONS = AUTH_DIR / "sessions.json"
MCP_JSON = Path.home() / ".cursor" / "mcp.json"
TOKEN_FILE = Path("/tmp/feishu_tokens.json")
REDIRECT = "http://127.0.0.1:8765/auth/feishu/callback"
COOKIE = "kap_session"
OAUTH_STATE: dict[str, float] = {}
ROLES = {"admin": "管理员", "user": "普通账号"}


def _read(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _users() -> list[dict]:
    return _read(USERS, [])


def _sessions() -> dict:
    return _read(SESSIONS, {})


def feishu_app() -> tuple[str, str]:
    mcp = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    args = mcp["mcpServers"]["lark"]["args"]
    return args[args.index("-a") + 1], args[args.index("-s") + 1]


def curl_json(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> dict:
    cmd = ["curl", "-sS", "-X", method, url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body, ensure_ascii=False)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return {"code": -1, "msg": (p.stderr or "curl failed")[:200]}
    try:
        return json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        return {"code": -1, "msg": "bad json"}


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()
    return salt, digest


def _role(u: dict) -> str:
    r = u.get("role")
    if r in ("admin", "OWNER"):
        return "admin"
    if r in ("user", "OPERATOR", "VIEWER"):
        return "user"
    return "admin"


def is_admin(u: dict | None) -> bool:
    return bool(u) and _role(u) == "admin"


def public_user(u: dict) -> dict:
    role = _role(u)
    return {
        "id": u.get("id"),
        "name": u.get("name"),
        "username": u.get("username") or "",
        "source": u.get("source"),
        "avatar": u.get("avatar") or "",
        "email": u.get("email") or "",
        "open_id": u.get("open_id") or "",
        "role": role,
        "role_label": ROLES[role],
        "is_admin": role == "admin",
        "status": u.get("status") or "approved",
    }


def list_users() -> list[dict]:
    return [public_user(u) for u in _users()]


def set_user_role(user_id: str, role: str) -> dict:
    if role not in ROLES:
        raise ValueError("角色只能是 admin 或 user")
    u = find_user(id=user_id)
    if not u:
        raise ValueError("用户不存在")
    if role == "user" and _role(u) == "admin":
        admins = [x for x in _users() if _role(x) == "admin"]
        if len(admins) <= 1:
            raise ValueError("至少保留一个管理员")
    u["role"] = role
    return public_user(upsert_user(u))


def approve_user(user_id: str) -> dict:
    u = find_user(id=user_id)
    if not u:
        raise ValueError("用户不存在")
    u["status"] = "approved"
    if not u.get("role"):
        u["role"] = "user"
    return public_user(upsert_user(u))


def find_user(**kwargs) -> dict | None:
    for u in _users():
        if all(u.get(k) == v for k, v in kwargs.items() if v is not None):
            return u
    return None


def upsert_user(user: dict) -> dict:
    rows = _users()
    for i, old in enumerate(rows):
        if old.get("id") == user["id"] or (
            user.get("open_id") and old.get("open_id") == user.get("open_id")
        ) or (user.get("username") and old.get("username") == user.get("username")):
            old.update(user)
            rows[i] = old
            _write(USERS, rows)
            return old
    rows.append(user)
    _write(USERS, rows)
    return user


def create_session(user: dict) -> str:
    sid = secrets.token_hex(24)
    data = _sessions()
    data[sid] = {"user_id": user["id"], "created": int(time.time())}
    _write(SESSIONS, data)
    return sid


def drop_session(sid: str) -> None:
    data = _sessions()
    data.pop(sid or "", None)
    _write(SESSIONS, data)


def user_by_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    rec = _sessions().get(sid)
    if not rec:
        return None
    u = find_user(id=rec.get("user_id"))
    return public_user(u) if u else None


def register_local(username: str, password: str, name: str) -> dict:
    username = (username or "").strip().split("@")[0]
    if not username or not password:
        raise ValueError("账号和密码不能空")
    if find_user(username=username):
        raise ValueError("账号已存在")
    salt, digest = hash_password(password)
    has_admin = any(_role(u) == "admin" for u in _users())
    user = {
        "id": "local-" + secrets.token_hex(6),
        "username": username,
        "name": name.strip() or username,
        "source": "local",
        "salt": salt,
        "password": digest,
        "avatar": "",
        "email": "",
        "open_id": "",
        "role": "user" if has_admin else "admin",
        "status": "approved",
    }
    return upsert_user(user)


def login_local(username: str, password: str) -> dict:
    u = find_user(username=(username or "").strip().split("@")[0])
    if not u or u.get("source") != "local":
        raise ValueError("账号或密码不对")
    _, digest = hash_password(password, u.get("salt") or "")
    if digest != u.get("password"):
        raise ValueError("账号或密码不对")
    if u.get("status") == "pending":
        raise ValueError("账号待管理员审核")
    return u


def authorize_url() -> str:
    app_id, _ = feishu_app()
    state = secrets.token_hex(12)
    OAUTH_STATE[state] = time.time() + 600
    return (
        "https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={quote(app_id)}&redirect_uri={quote(REDIRECT)}&state={state}"
    )


def app_access_token() -> str:
    app_id, app_secret = feishu_app()
    d = curl_json(
        "POST",
        "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
        body={"app_id": app_id, "app_secret": app_secret},
    )
    if d.get("code") not in (0, None) and not d.get("app_access_token"):
        raise ValueError(d.get("msg") or "app_access_token 失败")
    token = d.get("app_access_token")
    if not token:
        raise ValueError("没有 app_access_token")
    return token


def user_from_feishu_token(access_token: str) -> dict:
    d = curl_json(
        "GET",
        "https://open.feishu.cn/open-apis/authen/v1/user_info",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    data = d.get("data") or d
    name = data.get("name") or data.get("en_name") or "飞书用户"
    open_id = data.get("open_id") or data.get("union_id") or ""
    if not open_id and d.get("code") not in (0, None):
        raise ValueError(d.get("msg") or "读飞书用户失败")
    existing = find_user(open_id=open_id) if open_id else None
    has_admin = any(_role(u) == "admin" for u in _users())
    user = {
        "id": (existing or {}).get("id") or ("feishu-" + (open_id or secrets.token_hex(6))),
        "username": (existing or {}).get("username") or "",
        "name": name,
        "source": "feishu",
        "avatar": data.get("avatar_url") or "",
        "email": data.get("email") or data.get("enterprise_email") or "",
        "open_id": open_id,
        "role": _role(existing) if existing else ("admin" if not has_admin else "user"),
        "status": (existing or {}).get("status") or "approved",
    }
    saved = upsert_user(user)
    if saved.get("status") == "pending":
        raise ValueError("账号待管理员审核")
    return saved


def login_feishu_code(code: str, state: str) -> dict:
    exp = OAUTH_STATE.pop(state, 0)
    if not exp or exp < time.time():
        raise ValueError("登录状态过期，请再点一次飞书登录")
    app_token = app_access_token()
    d = curl_json(
        "POST",
        "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
        headers={"Authorization": f"Bearer {app_token}"},
        body={"grant_type": "authorization_code", "code": code},
    )
    data = d.get("data") or {}
    access = data.get("access_token")
    if not access:
        raise ValueError(d.get("msg") or "飞书换 token 失败，检查重定向 URL 是否已加到飞书后台")
    return user_from_feishu_token(access)


def login_feishu_local_token() -> dict:
    if not TOKEN_FILE.exists():
        raise ValueError("本机还没有飞书授权")
    tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    access = tok.get("access_token")
    if not access:
        raise ValueError("本机飞书 token 不完整")
    try:
        return user_from_feishu_token(access)
    except ValueError:
        script = Path.home() / ".cursor" / "skills" / "lark-jira-ops" / "scripts" / "refresh-feishu-token.sh"
        if script.exists():
            subprocess.run(["bash", str(script)], check=False, capture_output=True)
            tok = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            access = tok.get("access_token")
        if not access:
            raise
        return user_from_feishu_token(access)
