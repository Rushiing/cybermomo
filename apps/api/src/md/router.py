"""
02 · .md 创建 · API router

- POST /api/md            创建新档案(校验 v3 profile_json + 写入)
- GET  /api/md/me         返回当前用户的 active md_document

铁律体现:任何 endpoint 都 scoped to current_user;.md 内容只 host 自己可读。

Phase 0:用 mock auth(X-Mock-User-Id 头)
Phase 1 OAuth:替换 deps.get_current_user,这里逻辑不变
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import BackgroundTasks

from src.auth.deps import CurrentUser
from src.auth.models import User
from src.match import service as match_service
from src.md import service as md_service
from src.md.models import MdDocument
from src.md.schemas import CreateMdRequest, MdDocumentResponse
from src.shared.db import SessionLocal, get_session

router = APIRouter()


def _to_response(md: MdDocument) -> MdDocumentResponse:
    """把 ORM 实体打包成 API 响应(剥离 profile_json 大对象,只暴露关键摘要)"""
    portrait = md.profile_json.get("portrait", {}) if md.profile_json else {}
    return MdDocumentResponse(
        id=md.id,
        user_id=md.user_id,
        version=md.version,
        profile_version=md.profile_version,
        domains_interested=md.domains_interested or [],
        domains_avoided=md.domains_avoided or [],
        portrait_title=portrait.get("title", ""),
        portrait_body=portrait.get("body", []),
        is_active=md.is_active,
        created_at=md.created_at,
    )


async def _run_matching_async(user_id: int) -> None:
    """BackgroundTask:用独立 DB session 跑匹配"""
    async with SessionLocal() as db:
        try:
            await match_service.run_matching_for_user(db, user_id=user_id)
        except Exception as e:
            print(f"[match async] user_id={user_id} 跑匹配失败: {e}")


@router.post(
    "",
    response_model=MdDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_md(
    payload: CreateMdRequest,
    background_tasks: BackgroundTasks,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    用户提交 v3 profile_json。后端只做 schema 校验 + 入库,**不重新计算**。
    校验通过 + 同事务抽镜像列 + 失活旧版本 + 插入新版本 + 标 active。

    创建后**异步**触发匹配引擎(用 FastAPI BackgroundTasks,MVP 起步)。
    """
    md = await md_service.create_md_document(
        db,
        user_id=current_user.id,
        profile=payload.profile,
    )
    # 异步跑匹配,不阻塞 response
    background_tasks.add_task(_run_matching_async, current_user.id)
    return _to_response(md)


@router.get("/me", response_model=MdDocumentResponse)
async def get_my_md(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """返回当前用户的 active .md。"""
    md = await md_service.get_active_md_for_user(db, user_id=current_user.id)
    if md is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="还没有生成 .md 档案 — 先做完 17 题问卷",
        )
    return _to_response(md)
