"""
02 · .md 创建 · API router

Phase 0/1 阶段:
- POST /api/md            创建 .md(校验 v3 profile_json + 写入)
- GET  /api/me/md         返回当前用户的 active md_document
- (Phase 4 后)PATCH 或 重新创建支持 .md 修改

注:auth 还没实现,占位 user_id=None 由 auth dependency 注入。
当前 endpoints 全部 501,Phase 1 配合 auth 一起实装。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.md.schemas import CreateMdRequest, MdDocumentResponse
from src.shared.db import get_session

router = APIRouter()


@router.post(
    "",
    response_model=MdDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_md(
    payload: CreateMdRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    用户提交 v3 profile_json,服务端 schema 校验后入库。
    创建后 active 标记自动指向新版本(同 user 旧版本 is_active=false)。
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="POST /api/md 未实装 — Phase 1 接 auth + 写入逻辑后启用",
    )


@router.get("/me", response_model=MdDocumentResponse)
async def get_my_md(
    db: AsyncSession = Depends(get_session),
):
    """返回当前用户的 active .md(profile_version + portrait_body 等)"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="GET /api/md/me 未实装 — Phase 1 接 auth 后启用",
    )
