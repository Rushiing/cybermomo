import pytest

from src.auth.password import hash_password, verify_password


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
