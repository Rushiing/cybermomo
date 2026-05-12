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
    # 只有 POST /decision 接口在 decision='chat_with_my_agent' 时返回
    # 用于前端跳转 /me/agent/{conv_id}
    agent_conversation_id: Optional[int] = None


class DecisionRequest(BaseModel):
    decision: Literal["open_human_chat", "re_dispatch", "drop", "chat_with_my_agent"]
