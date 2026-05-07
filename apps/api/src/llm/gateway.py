"""
LLM 网关 · provider 抽象 + 路由 + 调用日志

业务模块**只调** `await llm_chat(role, messages, ...)`,不直接调 provider SDK。

Provider 路由表(MVP 写死,后续可改为从 DB 读 / 热更):
- 给 Agent 互聊 / 脱敏 / 内部分析:GLM-5(便宜、中文好)
- 给宿主侧 Agent(摘要 / 观察 / callout / 简报 / 全局对话):Claude(指令遵循 + 朋友式八卦语气稳)

GLM-5 走 dashscope 的 Anthropic 兼容端点,所以两个 provider 都用 Anthropic SDK。
"""
import time
from typing import Optional

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.types import ChatResponse, LLMRole, Message
from src.llm.models import LlmCallLog
from src.shared.settings import get_settings

# ========================================
# 路由表
# ========================================

# (provider, model)
_PROVIDER_BY_ROLE: dict[LLMRole, tuple[str, str]] = {
    "agent_chat":   ("glm5",   "glm-4-plus"),
    "desensitize":  ("glm5",   "glm-4-plus"),
    "summary":      ("claude", "claude-sonnet-4-5"),
    "prebriefing":  ("claude", "claude-sonnet-4-5"),
    "callout":      ("claude", "claude-sonnet-4-5"),
    "observation":  ("claude", "claude-sonnet-4-5"),
    "host_agent":   ("claude", "claude-sonnet-4-5"),
    "embedding":    ("zhipu",  "embedding-3"),  # 单独走 embedding 路径,见 embed.py
}


# ========================================
# Provider 客户端工厂(lazy 单例)
# ========================================

_clients_cache: dict[str, AsyncAnthropic] = {}


def _get_client(provider: str) -> AsyncAnthropic:
    """构造 Anthropic SDK 客户端(GLM-5 / Claude 共享 SDK)"""
    if provider in _clients_cache:
        return _clients_cache[provider]

    settings = get_settings()

    if provider == "glm5":
        if not settings.glm_api_key:
            raise RuntimeError("GLM_API_KEY 未配置")
        client = AsyncAnthropic(
            api_key=settings.glm_api_key,
            base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
        )
    elif provider == "claude":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 未配置")
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    else:
        raise ValueError(f"未知 provider: {provider}")

    _clients_cache[provider] = client
    return client


# ========================================
# 公共调用入口
# ========================================

async def llm_chat(
    *,
    role: LLMRole,
    messages: list[Message],
    system: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    # 调用日志关联(可选)
    db: Optional[AsyncSession] = None,
    user_id: Optional[int] = None,
    prompt_id: Optional[int] = None,
    related_table: Optional[str] = None,
    related_id: Optional[int] = None,
) -> ChatResponse:
    """
    异步调用 LLM。按 role 路由到对应 provider/model;调用结束自动写入 llm_call_log。

    传入 `db` 时会写日志;不传则只调用不写日志(适合脚本场景)。
    """
    provider, model = _PROVIDER_BY_ROLE[role]
    client = _get_client(provider)

    started = time.monotonic()
    error: Optional[str] = None
    text = ""
    input_tokens = output_tokens = None

    try:
        resp = await client.messages.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            system=system or "",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        input_tokens = resp.usage.input_tokens if resp.usage else None
        output_tokens = resp.usage.output_tokens if resp.usage else None
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)

        # 写调用日志(失败不影响主流程)
        if db is not None:
            try:
                log = LlmCallLog(
                    user_id=user_id,
                    role=role,
                    provider=provider,
                    model=model,
                    prompt_id=prompt_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    error=error,
                    related_table=related_table,
                    related_id=related_id,
                )
                db.add(log)
                await db.commit()
            except Exception as log_err:
                # 日志写失败不重抛
                print(f"[llm gateway] log write failed: {log_err}")

    return ChatResponse(
        text=text,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
