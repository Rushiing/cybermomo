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
    """对明文密码做 bcrypt 哈希,返回可直接存 DB 的字符串。

    rounds=10 是 OWASP 2024 推荐下限,Railway shared CPU 上 ~100-200ms;
    rounds=12 在我们的硬件上要 1-2s,注册请求慢得肉眼可见(实测 4.2s)。
    """
    if not plain:
        raise ValueError("password cannot be empty")
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(_prehash(plain), salt).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验密码;hashed 为 None 时直接 False(密码用户没绑密码不该到这)"""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("ascii"))
    except Exception:
        return False


# ========================================
# Timing-attack mitigation(用户不存在时也要跑 bcrypt 等耗时)
# ========================================
#
# 之前 login 的写法:user is None 直接 raise 401。问题是 bcrypt verify ~100ms,
# user 不存在跳过 bcrypt → 响应快几十毫秒,攻击者可以用 timing 探测用户名是否存在。
# 即使错误 detail 相同(都是 "用户名或密码错误"),timing channel 仍能区分。
#
# 修复:维护一个全局 dummy hash,user 不存在时也跑一次 verify_password(plain, dummy)
# (永远返 False),让两条路径耗时一致。
#
# dummy hash 用 lazy init —— 第一次 login 才生成,避免 import 时跑 bcrypt 拖慢启动。
_DUMMY_HASH: str | None = None


def _get_dummy_hash() -> str:
    """返回一个固定的合法 bcrypt hash 字符串,用于 timing 等耗。

    内容是个随机字符串的 hash,永远不会被任何真用户密码匹配上。
    rounds 跟 hash_password 一致,确保 verify 耗时一致。
    """
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("__cybermomo_dummy_for_timing_mitigation__")
    return _DUMMY_HASH


def verify_password_with_timing_mitigation(plain: str, hashed: str | None) -> bool:
    """跟 verify_password 一样,但 hashed=None 时也跑一次 bcrypt 让耗时一致。

    login endpoint 用这个 — user 不存在时也走 bcrypt 等耗,防 timing enumeration。
    其他场景(自己改密码、确认操作)用 verify_password 即可,不需要等耗。
    """
    if not plain:
        return False
    if hashed is None:
        # 跑 dummy 等耗,然后明确返 False
        bcrypt.checkpw(_prehash(plain), _get_dummy_hash().encode("ascii"))
        return False
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("ascii"))
    except Exception:
        return False
