"""
prompt 取用 helper

业务模块只持 (module, prompt_name),运行时从 prompt_versions 表拉 active 版本的 content。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.llm.models import PromptVersion


class PromptNotFoundError(RuntimeError):
    """没有 active 版本的 prompt"""


async def get_active_prompt(
    db: AsyncSession,
    *,
    module: str,
    prompt_name: str,
) -> PromptVersion:
    """
    取 (module, prompt_name) 当前 active 的 prompt。

    Raises:
        PromptNotFoundError: 找不到 active 版本
    """
    stmt = (
        select(PromptVersion)
        .where(
            PromptVersion.module == module,
            PromptVersion.prompt_name == prompt_name,
            PromptVersion.is_active.is_(True),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    pv = result.scalar_one_or_none()
    if pv is None:
        raise PromptNotFoundError(
            f"no active prompt for ({module}, {prompt_name})"
        )
    return pv
