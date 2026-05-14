import time

import pytest

from src.auth.password import (
    hash_password,
    verify_password,
    verify_password_with_timing_mitigation,
)


async def test_hash_password_returns_bcrypt_hash():
    hashed = hash_password("abc")

    assert hashed.startswith("$2b$10$")


async def test_verify_password_accepts_correct_plain_and_rejects_wrong_plain():
    hashed = hash_password("abc")

    assert verify_password("abc", hashed) is True
    assert verify_password("wrong", hashed) is False


async def test_verify_password_with_none_hash_returns_false():
    assert verify_password("abc", None) is False


async def test_hash_password_uses_random_salt():
    first = hash_password("same-password")
    second = hash_password("same-password")

    assert first != second
    assert verify_password("same-password", first) is True
    assert verify_password("same-password", second) is True


async def test_long_unicode_password_survives_bcrypt_72_byte_limit():
    plain = "桃" * 200
    hashed = hash_password(plain)

    assert verify_password(plain, hashed) is True


async def test_hash_password_rejects_empty_string():
    with pytest.raises(ValueError, match="password cannot be empty"):
        hash_password("")


# ========================================
# Timing-attack mitigation
# ========================================


async def test_timing_mitigation_returns_false_for_none_hash():
    """user 不存在场景:hashed=None 时返 False(但内部跑了 dummy bcrypt 等耗)"""
    assert verify_password_with_timing_mitigation("any-password", None) is False


async def test_timing_mitigation_matches_real_verify_when_hash_present():
    """user 存在时行为等同 verify_password"""
    hashed = hash_password("correct")
    assert verify_password_with_timing_mitigation("correct", hashed) is True
    assert verify_password_with_timing_mitigation("wrong", hashed) is False


async def test_timing_mitigation_none_path_takes_similar_time_as_real_verify():
    """关键回归 test:hashed=None 的耗时跟真实 verify 在同一量级,防 timing enumeration。

    本地 bcrypt rounds=10 约 80-200ms。我们只验证 "None 路径耗时不显著低于真实 verify"
    — 具体说,None 路径耗时不能 < 真实 verify 的 30%(留宽放过抖动)。
    """
    hashed = hash_password("warmup")  # 预热 + 触发 dummy hash lazy init

    # warm-up 一次(JIT / cache),量第二次
    verify_password_with_timing_mitigation("anything", hashed)
    verify_password_with_timing_mitigation("anything", None)

    t0 = time.perf_counter()
    verify_password_with_timing_mitigation("anything", hashed)
    real_elapsed = time.perf_counter() - t0

    t0 = time.perf_counter()
    verify_password_with_timing_mitigation("anything", None)
    none_elapsed = time.perf_counter() - t0

    # None 路径不能比真实路径快太多 — 防止攻击者用 timing 探测用户名是否存在
    assert none_elapsed >= real_elapsed * 0.3, (
        f"timing channel still leaks: none={none_elapsed*1000:.1f}ms "
        f"vs real={real_elapsed*1000:.1f}ms"
    )
