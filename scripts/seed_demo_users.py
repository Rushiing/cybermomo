#!/usr/bin/env python3
"""
Demo seeder · 一键创建 3 个差异化的 mock 用户 + POST /api/md 触发完整 pipeline

用法:
    python scripts/seed_demo_users.py
    API_URL=http://localhost:8787 python scripts/seed_demo_users.py
    USER_IDS=10,11,12 python scripts/seed_demo_users.py

POST 完会立即返回(pipeline 异步跑)。等 30-90s 后切对应 mock user 看 /api/summary/me。

依赖:Python 3.11+ stdlib(无外部依赖)
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime


API_URL = os.environ.get("API_URL", "https://cybermomo-production.up.railway.app").rstrip("/")
USER_IDS = [int(x) for x in os.environ.get("USER_IDS", "1,2,3").split(",")]


# ========================================
# 3 个档案原型
# ========================================

# 共用的 raw_answer 占位(不影响后端逻辑)
def _ra(idx: int, text: str = ""):
    return {"option_index": idx, "option_text": text}


def _profile(
    *,
    nickname: str,
    domains_interested: list[str],
    domains_avoided: list[str],
    dialogue: dict,
    boundary: dict,
    reliability: dict,
    conflict: dict,
    exploration: dict,
    agency: dict,
    warmth: dict,
    support: dict,
    connection: dict,
    portrait_title: str,
    portrait_body: list[str],
    portrait_tags: list[str],
) -> dict:
    return {
        "meta": {
            "version": "agent-social-portrait-17q-strong-combo",
            "generated_at": datetime.utcnow().isoformat() + "Z",
        },
        "domains": {"interested": domains_interested, "avoided": domains_avoided},
        "raw_answers": {qid: _ra(2) for qid in [
            "E1","E3","O3","CMM1","CMM2","CMM3","AU2","AV3","AX2","AU1",
            "CON4","CON2","ES3","ES2","O4","D1","D2",
        ]},
        "dialogue": dialogue,
        "relationship_warmth": {
            "warmth_initiation": warmth,
            "support_style": support,
            "connection_value": connection,
        },
        "boundary_and_closeness": boundary,
        "reliability": reliability,
        "conflict_repair": conflict,
        "exploration": exploration,
        "agency": agency,
        "portrait": {
            "title": portrait_title,
            "main_type": portrait_title.replace("你像是一个「", "").replace("」", ""),
            "title_reason": "demo seeder · 合成档案",
            "core_tension": portrait_body[0] if portrait_body else "",
            "tags": portrait_tags,
            "body": portrait_body,
            "debug": {"strongest_features": [], "picked_combos": [], "title_reason": "demo"},
        },
    }


PROFILES = {
    1: _profile(
        nickname="森屿",
        domains_interested=["AI与科技", "心理与人类观察", "文学写作", "历史社科"],
        domains_avoided=["时政公共议题", "体育赛事"],
        dialogue={"social_energy": 25, "sharing_drive": 78, "disagreement_exploration": 82},
        boundary={
            "interruption_sensitivity": 76, "arranged_decision_discomfort": 72,
            "closeness_density_pressure": 68, "coldness_sensitivity": 70,
        },
        reliability={"commitment_caution": 82, "notice_expectation": 84},
        conflict={"misunderstanding_regulation": 68, "emotional_recovery_speed": 30},
        exploration={"novelty_seeking": 60},
        agency={"task_initiation": 40, "decision_assertiveness": 64},
        warmth={"label": "留意但克制", "code": "attentive_reserved", "option_index": 2, "score": 33},
        support={"label": "问题理解型", "code": "problem_mapping", "option_index": 1},
        connection={"label": "共鸣连接", "code": "resonance_connection", "option_index": 2},
        portrait_title="你像是一个「不对所有人打开,但遇到同频会突然变亮的人」",
        portrait_body=[
            "你的社交入口不宽,但思考入口很深。聊点深的话题你会突然变得很想分享。",
            "你需要稳定回应感,但密度上来又会想后撤 — 要的是有呼吸感的靠近。",
        ],
        portrait_tags=["低频社交", "高分享欲", "观点探索", "共鸣连接"],
    ),
    2: _profile(
        nickname="雨季的鱼",
        domains_interested=["心理与人类观察", "文学写作", "影视综艺", "旅行城市", "生活方式"],
        domains_avoided=["神秘学与命理"],
        dialogue={"social_energy": 50, "sharing_drive": 60, "disagreement_exploration": 50},
        boundary={
            "interruption_sensitivity": 60, "arranged_decision_discomfort": 55,
            "closeness_density_pressure": 50, "coldness_sensitivity": 55,
        },
        reliability={"commitment_caution": 65, "notice_expectation": 70},
        conflict={"misunderstanding_regulation": 55, "emotional_recovery_speed": 50},
        exploration={"novelty_seeking": 65},
        agency={"task_initiation": 45, "decision_assertiveness": 50},
        warmth={"label": "轻触式关心", "code": "gentle_check_in", "option_index": 3, "score": 67},
        support={"label": "需求确认型", "code": "need_checking", "option_index": 2},
        connection={"label": "理解连接", "code": "mutual_understanding_connection", "option_index": 3},
        portrait_title="你像是一个「想被懂,但不想被过度进入的人」",
        portrait_body=[
            "你重视准确的理解多过单纯的热闹,但也愿意保持温暖的距离感。",
            "你能进入互动也能承受差异,只要氛围不是攻击性的。",
        ],
        portrait_tags=["温和", "理解连接", "中等节奏", "新体验趋近"],
    ),
    3: _profile(
        nickname="灯下白",
        domains_interested=["历史社科", "时政公共议题", "商业财经"],
        domains_avoided=["二次元动漫", "游戏"],
        dialogue={"social_energy": 60, "sharing_drive": 30, "disagreement_exploration": 80},
        boundary={
            "interruption_sensitivity": 40, "arranged_decision_discomfort": 30,
            "closeness_density_pressure": 40, "coldness_sensitivity": 35,
        },
        reliability={"commitment_caution": 50, "notice_expectation": 60},
        conflict={"misunderstanding_regulation": 60, "emotional_recovery_speed": 70},
        exploration={"novelty_seeking": 35},
        agency={"task_initiation": 80, "decision_assertiveness": 85},
        warmth={"label": "低介入关心", "code": "low_intervention", "option_index": 1, "score": 0},
        support={"label": "问题理解型", "code": "problem_mapping", "option_index": 1},
        connection={"label": "协作连接", "code": "collaborative_connection", "option_index": 1},
        portrait_title="你像是一个「能把事情推起来,也不会随便许诺的人」",
        portrait_body=[
            "你能进热闹但不爱自我暴露,组织事情比经营关系来得自然。",
            "你判断有把握时会希望别人认真考虑你的方向。",
        ],
        portrait_tags=["高推进", "判断有立场", "协作连接", "低分享欲"],
    ),
}


def post_md(user_id: int, profile: dict) -> tuple[int, str]:
    body = json.dumps({"profile": profile}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/api/md",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Mock-User-Id": str(user_id),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main() -> int:
    print(f"target API: {API_URL}")
    print(f"users: {USER_IDS}")
    print()

    # 取 USER_IDS 的前 N 个,每个映射到 PROFILES 中的一个原型
    available_profiles = list(PROFILES.values())
    if len(USER_IDS) > len(available_profiles):
        print(f"⚠️  最多支持 {len(available_profiles)} 个用户(不同档案)。多的会复用第 1 个。")

    for i, uid in enumerate(USER_IDS):
        profile = available_profiles[i] if i < len(available_profiles) else available_profiles[0]
        print(f"→ POST /api/md as user_id={uid} ({profile['domains']['interested'][:2]}...)")
        status, body = post_md(uid, profile)
        if status in (200, 201):
            data = json.loads(body)
            print(f"  ✓ md_id={data.get('id')} version={data.get('version')} title={data.get('portrait_title','')[:50]}")
        else:
            print(f"  ✗ HTTP {status}")
            print(f"    body: {body[:300]}")
        print()

    print("✓ 全部提交完。pipeline 在后台跑(匹配 → 脱敏 → 互聊 → 摘要),约 30-90s 完成。")
    print()
    print("接着试:")
    print(f"  curl -H 'X-Mock-User-Id: {USER_IDS[0]}' {API_URL}/api/summary/me")
    print(f"  curl -H 'X-Mock-User-Id: {USER_IDS[0]}' {API_URL}/api/match/me")
    return 0


if __name__ == "__main__":
    sys.exit(main())
