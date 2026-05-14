# Review · 2fb8809 perf(auth): /register 4.2s -> ~0.5s

**Reviewer**: CodeX
**Date**: 2026-05-14
**Verdict**: 通过

## 1. 变更摘要

这个 commit 把密码哈希 bcrypt rounds 从 12 降到 10,减少 Railway shared CPU 上的注册耗时;同时删除 register/login 的重复 SELECT,register 改用 `db.refresh(user)` 回填 server_default 字段,login 用 `selectinload(User.profile)` 一次拉出 profile。

## 2. 必修项(blocker)

- 无

## 3. 建议项(可选优化)

- [ ] `apps/api/src/auth/router.py:218`: login 对不存在用户会跳过 bcrypt,对错密码用户会执行 bcrypt,虽然响应都是 401,但仍有 timing enumeration 信号。建议后续加固定 dummy hash,在 user 不存在时也跑一次 `verify_password` 或等价 bcrypt check。
- [ ] `apps/api/src/auth/password.py:32`: OWASP Password Storage Cheat Sheet 对 bcrypt 的说法是 work factor should be 10 or more,这里写“推荐下限”成立,但更准确的注释可以写成“官方可接受下限 + 按硬件压测选择”。

## 4. 安全性 / 边界 case 检查

- [x] 输入校验是否完备(SQL 注入 / XSS / SSRF / 数据 size): username/password 仍走 Pydantic 约束;查询使用 SQLAlchemy 参数化。
- [x] auth / authz 是否正确: register 写 session cookie;login 仍要求密码校验通过。
- [x] DB 事务边界是否合理: register commit 后 refresh user,IntegrityError rollback 路径保留。
- [x] error path 是否会泄漏内部信息: login detail 仍统一;register 的冲突文案会暴露用户名占用,这是注册场景预期行为。

## 5. 性能检查

- [x] N+1 query: login 用 `selectinload(User.profile)` 明确避免 lazy load;register 不再额外 SELECT。
- [x] 不必要的 await / round-trip: 删除了 register/login 的冗余重拉。
- [x] 长任务有没有阻塞 event loop: bcrypt 仍是同步 CPU work,但 rounds=10 降低了阻塞时间;MVP 可接受。
- [x] DB 连接池占用: 没有新增长连接持有;round-trip 减少。

## 6. 与 AGENTS.md §3 铁律的兼容性

- [x] §3.1 平台底线 vs Agent 拉黑数据隔离: 不涉及。
- [x] §3.2 Agent 行为约束在平台 prompt: 不涉及。
- [x] §3.3 朋友式八卦语气: 不涉及,这是 auth API 系统文案。
- [x] §3.4 .md 不向他人暴露: 不涉及。
- [x] §3.5 prompt 改动权限: 不涉及。

## 7. 测试覆盖建议(为 Task A 准备的)

- `hash_password("abc")` 产出 bcrypt 格式串,并且 rounds 成本参数是 10。
- 同一明文两次 hash 结果不同,但都能 verify。
- 200 字符中文密码能 hash + verify,覆盖 sha256 + base64 预处理。
- `POST /register` happy path 返回 201/200 语义按当前实现确认,带 session cookie 和完整 `UserMeResponse`。
- 带 nickname 注册时 DB 里创建 `UserProfile`,不带 nickname 时不创建。
- 重复 username register 返回 409。
- login 正确密码返回 session cookie;错密码和不存在用户都返回同一 401 detail。
- 注册后立刻 `/me` 能拿到 `created_at` / `is_adult_confirmed` / `google_avatar_url` 字段。
