"""
LLM 网关 · 测试期统一走 百炼(DashScope)OpenAI-compatible 端点

- base_url:https://dashscope.aliyuncs.com/compatible-mode/v1
- 默认模型:deepseek-v4-flash(LLM_MODEL env 覆盖)
- API 密钥:DASHSCOPE_API_KEY(fallback GLM_API_KEY)

业务模块只调 `await llm_chat(role, messages, system=..., db=...)`,
不直接调 SDK。Provider 路由表保留(目前所有 role 都指向 deepseek-v4-flash),
后续要按 role 切模型只改这一处即可。
"""
import time
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.types import ChatResponse, LLMRole, Message
from src.llm.models import LlmCallLog
from src.shared.settings import get_settings


# ========================================
# 路由表 — 所有 role 指向 deepseek-v4-flash(测试期单一模型)
# ========================================

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _model_for_role(role: LLMRole) -> str:
    """
    role → model 路由。
    测试期所有 role 走 settings.llm_model(默认 deepseek-v4-flash)。
    后续要按 role 切模型,在这里加分支。
    """
    settings = get_settings()
    if role == "embedding":
        # 测试期暂不用 embedding(matching 走纯 compute)
        # 真要用走 dashscope text-embedding-v3
        return "text-embedding-v3"
    return settings.llm_model


# ========================================
# Provider 客户端(单例)
# ========================================

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    api_key = settings.effective_dashscope_key
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY(或 GLM_API_KEY)未配置")
    _client = AsyncOpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)
    return _client


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
    异步调用 LLM。OpenAI-compatible 接口。
    传入 `db` 时会写 llm_call_log;不传则只调用不写日志(适合脚本场景)。
    """
    model = _model_for_role(role)
    client = _get_client()

    # 拼 OpenAI 格式 messages(system 是第一条,不是 kwarg)
    api_messages: list[dict] = []
    if system:
        api_messages.append({"role": "system", "content": system})
    for m in messages:
        api_messages.append({"role": m.role, "content": m.content})

    started = time.monotonic()
    error: Optional[str] = None
    text = ""
    input_tokens = output_tokens = None

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0] if resp.choices else None
        text = (choice.message.content or "") if choice else ""
        if resp.usage:
            input_tokens = resp.usage.prompt_tokens
            output_tokens = resp.usage.completion_tokens
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
                    provider="dashscope",
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
                print(f"[llm gateway] log write failed: {log_err}")

    return ChatResponse(
        text=text,
        model=model,
        provider="dashscope",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
