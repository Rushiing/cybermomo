"""
冷启动 mock 用户档案 fixture · 兼容入口

源数据已搬到 `apps/api/src/seed/archetypes.py`(为了让 Railway api 容器也能
import — Dockerfile 只 COPY apps/api/,不带 scripts/)。

本文件保留只是兼容旧引用 + 让你可以从仓库根独立打印 20 人摘要:
    python3 scripts/mock_user_archetypes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_ROOT = _REPO_ROOT / "apps" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from src.seed.archetypes import MOCK_USERS, build_profile_for  # noqa: F401, E402


if __name__ == "__main__":
    import json

    print(f"mock users: {len(MOCK_USERS)}\n")
    archetype_count: dict[str, int] = {}
    for u in MOCK_USERS:
        archetype_count[u["archetype"]] = archetype_count.get(u["archetype"], 0) + 1
        print(f"  {u['username']:<24} {u['nickname']:<6} "
              f"{u['age_band']:<6} {u['gender']:<14} {u['mbti']:<5} "
              f"· {u['archetype']}")
    print("\narchetype 分布:")
    for k, v in archetype_count.items():
        print(f"  {k}: {v}")

    print("\n第一人完整 profile (head):")
    p = build_profile_for(MOCK_USERS[0])
    print(json.dumps({
        "domains": p["domains"],
        "dialogue": p["dialogue"],
        "portrait_title": p["portrait"]["title"],
    }, ensure_ascii=False, indent=2))
