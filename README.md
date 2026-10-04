# 快记自动化测试平台

真机点检收成平台：用例库、执行结果、测试报告。断言写进每条用例，报告出 JSON / HTML / JUnit。

仓库：https://github.com/toviaz/kuaiji-auto-platform  
介绍页：https://toviaz.github.io/kuaiji-auto-platform/

来源：[每日点检](https://wvixbzgc0u7.feishu.cn/wiki/EFdgwGeyBi4kDqkOIolcbg8bnOc)

## 控制台

```bash
cd ~/Desktop/kuaiji-auto-platform
.venv/bin/python -m app web
```

打开 http://127.0.0.1:8765 ，先登录。支持飞书登录和本机账号。

飞书后台要把重定向 URL 加上：`http://127.0.0.1:8765/auth/feishu/callback`  
配置页：https://open.feishu.cn/app/cli_aaa25e5537385bc9/safe

本机已经授过飞书的，登录页也可以点「用本机已有飞书授权」。

四个业务页可互相跳转。

| 地址 | 页 |
|---|---|
| `/` | 概览 |
| `/cases` | 用例列表 |
| `/cases/KJ-06` | 单条用例（步骤 / 断言 / 历史） |
| `/results` | 执行结果列表 |
| `/report/<run_id>` | 单次报告 |

当前先看演示数据，真机执行后开。

## 目录

- `app/catalog.py` 用例库
- `app/cases/smoke_kj.py` 真机步骤 + 软断言
- `app/assertlib.py` 软断言
- `app/runner.py` 跑套件
- `app/report.py` JSON / HTML / JUnit
- `data/runs/<run_id>/` 每次产物

## 断言

- 任一条失败 → FAIL
- 全部通过 → PASS
- 用例标 SKIP / MANUAL → 保持
