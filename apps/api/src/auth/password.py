"""
密码哈希工具 · passlib + bcrypt

注:bcrypt rounds 默认 12,Railway 镜像够快(单次 ~100ms)。
"""
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希,返回可直接存 DB 的字符串"""
    if not plain:
        raise ValueError("password cannot be empty")
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验密码;hashed 为 None 时直接 False(密码用户没绑密码不该到这)"""
    if not plain or not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False
