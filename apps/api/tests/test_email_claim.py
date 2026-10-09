from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from src.auth.models import EmailAccountClaim, User, UserProfile
from src.auth.password import hash_password
from src.auth.session import verify_session_token
from src.auth import email_claim

async def legacy(db, **extra):
    user = User(email="old@example.test", google_sub="original", **extra)
    db.add(user)
    await db.flush()
    db.add(UserProfile(user_id=user.id, nickname="Original profile"))
    await db.commit()
    return user.id

@pytest.fixture
def mail(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(email_claim, "send_claim_mail", mock)
    return mock

async def request(client):
    return await client.post("/api/auth/email-claim/request", json={"email": " OLD@EXAMPLE.TEST "})

async def confirm(client, token, username="restored"):
    return await client.post("/api/auth/email-claim/confirm", json={"email":"old@example.test", "token":token, "username":username, "password":"strong-password"})

async def test_identity_history_cookie_login_and_single_use(client, db_session, mail):
    uid = await legacy(db_session)
    assert (await request(client)).status_code == 200
    token = mail.call_args.args[1]
    claim = await db_session.get(EmailAccountClaim, uid)
    assert claim.token_hash != token and len(claim.token_hash) == 64
    response = await confirm(client, token)
    assert response.status_code == 200
    assert verify_session_token(response.cookies["cm_session"]) == uid
    me = (await client.get("/api/auth/me")).json()
    assert me["id"] == uid and me["profile"]["nickname"] == "Original profile"
    assert (await confirm(client, token)).status_code == 400
    result = await client.post("/api/auth/login", json={"username":"restored", "password":"strong-password"})
    assert result.status_code == 200 and result.json()["id"] == uid

async def test_password_unknown_deleted_are_not_claimable(client, db_session, mail):
    uid = await legacy(db_session, username="already", password_hash=hash_password("password"))
    assert (await request(client)).json() == {"detail":email_claim.NOTICE}
    unknown = await client.post("/api/auth/email-claim/request", json={"email":"unknown@example.test"})
    assert unknown.json() == {"detail":email_claim.NOTICE}
    user = await db_session.get(User, uid)
    user.password_hash = None
    user.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    await request(client)
    mail.assert_not_called()

async def test_cooldown_daily_limit_and_rotation(client, db_session, mail):
    uid = await legacy(db_session)
    await request(client)
    first = mail.call_args.args[1]
    await request(client)
    assert mail.call_count == 1
    claim = await db_session.get(EmailAccountClaim, uid)
    claim.requested_at = datetime.now(timezone.utc)-timedelta(seconds=61)
    await db_session.commit()
    await request(client)
    assert mail.call_count == 2 and mail.call_args.args[1] != first
    assert (await confirm(client, first)).status_code == 400
    await db_session.refresh(claim)
    claim.requested_at = datetime.now(timezone.utc)-timedelta(seconds=61)
    claim.send_count = 5
    await db_session.commit()
    await request(client)
    assert mail.call_count == 2

async def test_wrong_expired_and_username_conflict(client, db_session, mail):
    uid = await legacy(db_session)
    db_session.add(User(username="taken", password_hash=hash_password("password")))
    await db_session.commit()
    await request(client)
    token = mail.call_args.args[1]
    assert (await confirm(client, "a"*43)).status_code == 400
    assert (await confirm(client, token, "taken")).status_code == 409
    claim = await db_session.get(EmailAccountClaim, uid)
    claim.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    await db_session.commit()
    assert (await confirm(client, token)).status_code == 400

async def test_unverified_email_cannot_claim_password_account(client, db_session, mail):
    uid = await legacy(db_session)
    db_session.add(User(username="attacker", email="old@example.test", password_hash=hash_password("password")))
    await db_session.commit()
    await request(client)
    response = await confirm(client, mail.call_args.args[1])
    assert response.status_code == 200 and verify_session_token(response.cookies["cm_session"]) == uid

async def test_mail_failure_retains_budget_without_leaking_errors(client, db_session, mail):
    uid = await legacy(db_session)
    mail.side_effect = RuntimeError("secret transport details")
    result = await request(client)
    assert result.status_code == 503 and "secret" not in result.text
    assert (await db_session.get(EmailAccountClaim, uid)).send_count == 1

async def test_malformed_input_rejected(client):
    assert (await client.post("/api/auth/email-claim/request", json={"email":"bad\nheader"})).status_code == 422
    assert (await confirm(client, "short")).status_code == 422

async def test_duplicate_google_emails_fail_closed(client, db_session, mail):
    await legacy(db_session)
    db_session.add(User(email="OLD@example.test", google_sub="another-google"))
    await db_session.commit()
    assert (await request(client)).status_code == 200
    mail.assert_not_called()
    assert (await confirm(client, "a"*43)).status_code == 400
