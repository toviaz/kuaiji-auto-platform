async function api(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function pill(s) {
  return s ? `<span class="pill ${s}">${s}</span>` : "";
}

function pills(sum) {
  if (!sum) return "";
  return ["PASS", "FAIL", "SKIP", "MANUAL"]
    .map((k) => `<span class="pill ${k}">${k} ${sum[k] || 0}</span>`)
    .join(" ");
}

let CURRENT_USER = null;
let ACTIVE_PAGE = "overview";

function nav(active) {
  const items = [
    ["/", "overview", "概览"],
    ["/cases", "cases", "用例"],
    ["/results", "results", "执行结果"],
    ["/report", "report", "报告"],
  ];
  if (CURRENT_USER && CURRENT_USER.is_admin) {
    items.push(["/users", "users", "用户管理"]);
  }
  return items
    .map(([href, key, name]) => `<a href="${href}" class="${key === active ? "on" : ""}">${name}</a>`)
    .join("");
}

const PAGE_TITLES = {
  overview: "概览",
  cases: "用例",
  results: "执行结果",
  report: "报告",
  account: "账号",
  users: "用户管理",
};

function paintNav() {
  const navEl = document.getElementById("site-nav");
  if (navEl) navEl.innerHTML = nav(ACTIVE_PAGE);
}

function header(active, meta = "") {
  ACTIVE_PAGE = active;
  const title = PAGE_TITLES[active] || meta || "快记自动化测试平台";
  const top = document.querySelector("header .top");
  if (top) {
    top.innerHTML = `
      <div class="page-title">${title}</div>
      <div class="user-area" id="header-user"></div>`;
  }
  paintNav();
  renderUser();
}

async function renderUser() {
  const box = document.getElementById("header-user");
  if (!box) return;
  try {
    const d = await api("/api/auth/me");
    const u = d.user;
    CURRENT_USER = u;
    paintNav();
    if (!u) {
      box.innerHTML = `<a href="/login">登录</a>`;
      return;
    }
    box.innerHTML = `
      <div class="user-info">
        <a class="user-name" href="/account">${u.name || u.username || "用户"}</a>
        <div class="user-role ${u.role || ""}">${u.role_label || "普通账号"}</div>
      </div>
      <a class="logout" href="#" id="logout-link">退出</a>`;
    document.getElementById("logout-link").onclick = async (e) => {
      e.preventDefault();
      await fetch("/api/auth/logout", { method: "POST" });
      location.href = "/login";
    };
  } catch (e) {
    CURRENT_USER = null;
    paintNav();
    box.innerHTML = `<a href="/login">登录</a>`;
  }
}

function go(url) {
  location.href = url;
}
