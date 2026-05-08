"""
07 · 真人聊天室 · API schema
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    match_id: int
    source_summary_id: Optional[int] = None  # 从哪张简报衍生而来(旧 session 可能为 NULL)
    user_a_id: int
    user_b_id: int
    status: str
    last_message_at: Optional[datetime] = None
    created_at: datetime


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    sender_user_id: int
    content_type: Literal["text", "image"]
    content: str
    sent_at: datetime


class SendMessageRequest(BaseModel):
    content_type: Literal["text", "image"] = "text"
    content: str = Field(min_length=1, max_length=4000)


class CalloutRequest(BaseModel):
    callout_prompt: str = Field(min_length=1, max_length=2000)
    context_message_ids: Optional[list[int]] = None  # 引用对方某条消息


class CalloutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    callout_prompt: str
    callout_response: str
    context_message_ids: Optional[list[int]] = None
    model: str
    created_at: datetime


class ExitRequest(BaseModel):
    action: Literal["quit", "block", "report"] = "quit"
    note: Optional[str] = None  # report 时的内容


class ChatBriefingResponse(BaseModel):
    """§4.9 真人聊天前简报"""
    summary_id: int
    verdict: str
    highlights: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    recommended_action: str
    evidence_chunks: list[dict[str, Any]] = []
    created_at: datetime
