"""
密码哈希工具 · 纯 bcrypt(放弃 passlib)

为什么不用 passlib:
  passlib 1.7.4 调用 bcrypt 库的内部 `__about__.__version__`,但 bcrypt 4.1+
  移除了这个属性 → AttributeError → uvicorn worker crash → Railway 进程重启
  → 前端 "Failed to fetch" / connection reset。
  passlib 上次发版 2020 已无人维护,直接换 bcrypt 直调更稳。

bcrypt 72-byte 输入限制:
  bcrypt 内部把超过 72 byte 的输入截断或在 4.x 直接抛 ValueError。
  我们 schema 限 password ≤ 100 字符,中文 utf-8 下可能 > 72 byte。
  预先 sha256 + base64 → 固定 44 byte ASCII,既规避限制又不损失熵。
"""
from __future__ import annotations

import base64
import hashlib

import bcrypt


def _prehash(plain: str) -> bytes:
    """sha256 → base64 编码,得到固定 44 byte ASCII,小于 bcrypt 72-byte 上限"""
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希,返回可直接存 DB 的字符串"""
    if not plain:
        raise ValueError("password cannot be empty")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(_prehash(plain), salt).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验密码;hashed 为 None 时直接 False(密码用户没绑密码不该到这)"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("ascii"))
    except Exception:
        return False
