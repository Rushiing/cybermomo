#!/usr/bin/env python3
"""
Railway Cron · observation sweep + Agent 回访

每 30 分钟跑一次:
- 扫 active 但 last_message_at > 24h 之前的 chat_sessions
- 标 ended_quit + 给双方观察报告 + 种 Agent 回访 conversation

环境变量:
- API_BASE       例:https://cybermomo-production.up.railway.app
- ADMIN_SECRET   跟 api 服务的 ADMIN_SECRET 同一个值

Railway 上配置:
1. 在同一 Project 加一个 Cron Service(可以指向同一仓库)
2. Settings → Cron Schedule:  *​/30 * * * *   (每 30 分钟)
3. Start Command:             python apps/api/scripts/cron_observation_sweep.py
4. Variables:                 API_BASE + ADMIN_SECRET(从 api 服务复制 ADMIN_SECRET)

或者用 curl(api Dockerfile 自带):
   curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" $API_BASE/api/admin/observation-sweep

退出码:0 成功 / 非 0 失败(Railway Cron 会留日志)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Python 在容器里 stdout 默认块缓冲,短命脚本退出太快 print 还没 flush
# 就被 Railway 收走,日志里看不到输出。强制 line-buffered。
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]


def main() -> int:
    api_base = os.environ.get("API_BASE", "").rstrip("/")
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if not api_base or not admin_secret:
        print("ERROR: API_BASE 和 ADMIN_SECRET 必须设置", file=sys.stderr)
        return 2

    url = f"{api_base}/api/admin/observation-sweep"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"X-Admin-Secret": admin_secret},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
                print(json.dumps(data, ensure_ascii=False))
            except Exception:
                print(body)
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTPError {e.code}: {body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
