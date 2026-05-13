"""
06 · Agent 简报 · API schema
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_chat_id: Optional[int] = None
    chat_session_id: Optional[int] = None
    host_user_id: int
    summary_type: str
    verdict: str
    highlights: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    recommended_action: str
    evidence_chunks: list[dict[str, Any]] = []
    created_at: datetime
    user_decision: Optional[str] = None  # 来自 summary_decisions
    decided_at: Optional[datetime] = None
    # 这张简报关于谁(对方)— 前端卡片标题用
    # agent_chat / pre_briefing:来自 agent_chat → match
    # human_chat_observation:来自 chat_session
    peer_user_id: Optional[int] = None
    peer_nickname: Optional[str] = None
    # 该简报关联的「跟我 Agent 聊聊」对话 id(没有的话是 null)
    # 跟「decision」无关 — 任何时候卡片上「跟我 Agent 聊聊」按钮都用它跳
    agent_conversation_id: Optional[int] = None


class DecisionRequest(BaseModel):
    # 注:chat_with_my_agent 已不再是 decision(它是持续性"沉思"行为,
    # 单独走 POST /api/summary/{id}/agent-chat)
    decision: Literal["open_human_chat", "re_dispatch", "drop"]
    # 仅 re_dispatch 时使用 — 宿主在 Agent 对话里沉淀的方向 hint,
    # 传给下一场 agent 互聊
    direction_hint: Optional[str] = None
