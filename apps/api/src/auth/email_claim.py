"""Recover Google-only accounts after proving ownership of their original email."""
import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from src.auth.models import EmailAccountClaim, User
from src.auth.password import hash_password
from src.auth.schemas import EmailClaimRequest, EmailClaimConfirm
from src.auth.session import set_session_cookie
from src.shared.db import get_session
from src.shared.settings import get_settings

router = APIRouter(prefix="/api/auth/email-claim", tags=["auth"])
NOTICE = "若该邮箱关联待恢复的旧 Google 账号，验证邮件将发送到原邮箱。请检查收件箱及垃圾邮件，60 秒后可重试。"


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def send_claim_mail(email: str, token: str):
    s = get_settings()
    if not all([s.smtp_host, s.smtp_username, s.smtp_password, s.claim_mail_from]):
        raise RuntimeError("Mail is not configured")
    msg = EmailMessage()
    msg["From"] = formataddr(("CyberMOMO", s.claim_mail_from))
    msg["To"] = email
    msg["Subject"] = "CyberMOMO 旧账号验证"
    msg.set_content(f"你正在找回 CyberMOMO 旧账号。\n\n验证口令：{token}\n\n请在找回页面填写口令并设置用户名和密码。口令15分钟内有效，仅能使用一次。若非本人操作，请忽略此邮件。")
    context = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=10, context=context) as smtp:
            smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.starttls(context=context)
            smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)


async def eligible_user(db, email):
    # Password registrations contain unverified email addresses: never claim them.
    users = (await db.execute(select(User).where(
        func.lower(func.trim(User.email)) == email,
        User.google_sub.is_not(None), User.password_hash.is_(None), User.deleted_at.is_(None),
    ).with_for_update())).scalars().all()
    return users[0] if len(users) == 1 else None


@router.post("/request")
async def request_claim(payload: EmailClaimRequest, db: AsyncSession = Depends(get_session)):
    user = await eligible_user(db, payload.email)
    if user is None:
        return {"detail": NOTICE}
    now = datetime.now(timezone.utc)
    claim = await db.get(EmailAccountClaim, user.id)
    if claim and (now - utc(claim.requested_at) < timedelta(seconds=60)
                  or (now - utc(claim.window_start) < timedelta(days=1) and claim.send_count >= 5)):
        return {"detail": NOTICE}
    token = secrets.token_urlsafe(32)
    if claim is None:
        claim = EmailAccountClaim(user_id=user.id, window_start=now, send_count=0)
        db.add(claim)
    if now - utc(claim.window_start) >= timedelta(days=1):
        claim.window_start, claim.send_count = now, 0
    claim.token_hash = hashlib.sha256(token.encode()).hexdigest()
    claim.requested_at, claim.expires_at = now, now + timedelta(minutes=15)
    claim.consumed_at = None
    claim.send_count += 1
    await db.commit()  # Persist rate budget before SMTP; ambiguous sends are never retried automatically.
    try:
        await run_in_threadpool(send_claim_mail, payload.email, token)
    except Exception:
        raise HTTPException(503, "验证邮件暂时无法发送，请稍后重试") from None
    return {"detail": NOTICE}


@router.post("/confirm")
async def confirm_claim(payload: EmailClaimConfirm, db: AsyncSession = Depends(get_session)):
    user = await eligible_user(db, payload.email)
    claim = await db.get(EmailAccountClaim, user.id) if user else None
    now = datetime.now(timezone.utc)
    if (claim is None or claim.consumed_at is not None or utc(claim.expires_at) <= now
            or not secrets.compare_digest(claim.token_hash, hashlib.sha256(payload.token.encode()).hexdigest())):
        raise HTTPException(400, "验证口令无效或已过期，请重新申请")
    if user.username is not None and user.username != payload.username:
        raise HTTPException(409, "请使用原账号用户名")
    conflict = (await db.execute(select(User.id).where(
        User.username == payload.username, User.id != user.id))).scalar_one_or_none()
    if conflict is not None:
        raise HTTPException(409, "用户名已被占用，请换一个")
    user.username = payload.username
    user.password_hash = await run_in_threadpool(hash_password, payload.password)
    claim.consumed_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "用户名已被占用，请换一个") from None
    response = JSONResponse({"ok": True})
    set_session_cookie(response, user.id)
    return response
