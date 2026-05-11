"""
LLM 网关 · 公共类型
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

# Agent 调用场景 → 用于路由 provider/model
LLMRole = Literal[
    "agent_chat",     # Agent 互聊(.md 注入)
    "desensitize",    # 脱敏 Agent(matchpoints → hooks)
    "summary",        # Agent 互聊后简报
    "prebriefing",    # 真人聊天前简报(§4.9)
    "callout",        # 真人聊天里的旁观者 callout
    "observation",    # 真人聊天后观察报告
    "host_agent",     # 与自己 Agent 的对话(§4.10 · 全局)
    "embedding",      # 向量
]


class Message(BaseModel):
    """OpenAI/Anthropic 兼容的 message 格式"""
    role: Literal["user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    """LLM chat 调用产物"""
    text: str
    model: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    cost_estimate: float | None = None
    raw: dict[str, Any] | None = Field(default=None, exclude=True)


class EmbeddingResponse(BaseModel):
    """LLM embedding 调用产物 — 单条文本"""
    vector: list[float]
    dim: int
    model: str
    provider: str
    input_tokens: int | None = None
    latency_ms: int | None = None
