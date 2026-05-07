"""
02 · .md 创建 · 业务逻辑

- create_md_document:
    1. 校验 v3 profile_json schema(由 router 层 Pydantic 完成)
    2. 抽镜像列(domains_interested / domains_avoided / portrait_body)
    3. 如果该用户已有 active 档案 → is_active=false
    4. 计算下个 version
    5. 插入新行,is_active=true

- get_active_md_for_user:返回当前 user 的 active 档案

档案不可单字段编辑(v3 设计):任何修改 = 重做问卷 + 整体覆盖。
"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.md.models import MdDocument
from src.md.schemas import ProfileV3


async def create_md_document(
    db: AsyncSession,
    *,
    user_id: int,
    profile: ProfileV3,
) -> MdDocument:
    """创建新的 .md 档案,标 active,前一版本自动 is_active=false。"""
    # 上一版本失活
    await db.execute(
        update(MdDocument)
        .where(MdDocument.user_id == user_id, MdDocument.is_active.is_(True))
        .values(is_active=False)
    )

    # 算 version
    last_version_stmt = select(func.coalesce(func.max(MdDocument.version), 0)).where(
        MdDocument.user_id == user_id
    )
    next_version = (await db.execute(last_version_stmt)).scalar_one() + 1

    # 抽镜像列(domains + portrait_body)
    profile_dict = profile.model_dump(mode="json")
    portrait_body_text = "\n\n".join(profile.portrait.body)

    md = MdDocument(
        user_id=user_id,
        version=next_version,
        profile_json=profile_dict,
        profile_version=profile.meta.version,
        portrait_body=portrait_body_text,
        domains_interested=profile.domains.interested,
        domains_avoided=profile.domains.avoided,
        raw_answers={k: v.model_dump(mode="json") for k, v in profile.raw_answers.items()},
        is_active=True,
    )
    db.add(md)
    await db.commit()
    await db.refresh(md)
    return md


async def get_active_md_for_user(
    db: AsyncSession,
    *,
    user_id: int,
) -> MdDocument | None:
    """返回 user 当前 active 的 .md;若不存在返 None"""
    stmt = (
        select(MdDocument)
        .where(MdDocument.user_id == user_id, MdDocument.is_active.is_(True))
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
