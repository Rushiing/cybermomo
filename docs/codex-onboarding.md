# CodeX Onboarding · 第一批任务(2026-05-13)

> 欢迎接入 CyberMOMO 项目。先看 [`AGENTS.md`](../AGENTS.md) 全文,这里是你第一批要做的活的详细 brief。
>
> 完成顺序:**先 B 后 A**(B 是 review 工作能让你先读懂代码再动手写测试)。

---

## 前置准备(只跑一次)

### 1. 配 git 身份(commit author)

```bash
cd /path/to/cybermomo-app
git config user.name "CodeX"
git config user.email "codex@cybermomo.local"
```

### 2. 验证开发环境

```bash
# Python 3.11+
python3 --version

# 装依赖
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx aiosqlite  # test 依赖

# 本地 DB
cd ../..
docker-compose up -d

# alembic
cd apps/api && alembic upgrade head

# 跑一下 API 起不起得来
uvicorn main:app --port 8787 &
curl http://localhost:8787/healthz
```

---

## Task B · Review 已合并 commit(先做这个)

### 范围

最近这 3 个 commit,由 Claude 直推 main,**没有 review pass**。需要你独立审一遍。

```bash
# 看 commit list
git log --oneline -10

# 重点这 3 个
git show 2fb8809   # perf(auth): /register 4.2s → ~0.5s
git show 2c73f6a   # feat(avatar): 头像上传启用
git show bc67b32   # fix(mbti): 默认不勾「不知道 / 不想填」
```

### 你要做的

为每个 commit 写一份 review 报告,放在 `docs/reviews/`:

```
docs/reviews/
├── 2fb8809-perf-auth-register.md
├── 2c73f6a-feat-avatar-upload.md
└── bc67b32-fix-mbti-default.md
```

### 每份报告的格式(必须)

```markdown
# Review · <commit_hash> <commit_title>

**Reviewer**: CodeX
**Date**: 2026-05-13
**Verdict**: ✅ 通过 / ⚠️ 有问题需修 / ❌ 必须回退

## 1. 变更摘要(你读完代码的理解,30-100 字)
...

## 2. 必修项(blocker)
- [ ] (如有,写出具体问题 + 文件:行号 + 建议修法)
- (没有就写"无")

## 3. 建议项(可选优化)
- [ ] ...

## 4. 安全性 / 边界 case 检查
- [ ] 输入校验是否完备(SQL 注入 / XSS / SSRF / 数据 size)
- [ ] auth / authz 是否正确
- [ ] DB 事务边界是否合理
- [ ] error path 是否会泄漏内部信息

## 5. 性能检查
- [ ] N+1 query
- [ ] 不必要的 await / round-trip
- [ ] 长任务有没有阻塞 event loop
- [ ] DB 连接池占用

## 6. 与 AGENTS.md §3 铁律的兼容性
- [ ] §3.1 平台底线 vs Agent 拉黑数据隔离 — 涉及? 是否合规?
- [ ] §3.2 Agent 行为约束在平台 prompt — 涉及? 是否合规?
- [ ] §3.3 朋友式八卦语气 — 涉及? 是否合规?
- [ ] §3.4 .md 不向他人暴露 — 涉及? 是否合规?
- [ ] §3.5 prompt 改动权限 — 涉及? 是否合规?

(不涉及的写"不涉及",涉及的明确判定)

## 7. 测试覆盖建议(为 Task A 准备的)
- 应该补哪些 test case 来锁这次改动的边界?
- 列 3-8 条
```

### 重点关注的几个角度(基于我对这 3 个 commit 的了解,给你 hint)

#### `2fb8809` — register 提速
- bcrypt rounds 12 → 10,**OWASP 2024 是不是真这么推荐?** 查一下。如果不是,把 hint 反过来给 Claude
- `db.refresh(user)` 在 SQLAlchemy 2.0 async 下,server_default 字段(`is_adult_confirmed` / `created_at`)是不是真的会回来? 还是需要 `selectinload` 一并拉?
- `login` 那段从两次 SELECT 改成 selectinload,**eager load 后 user.profile 是不是真的有值?** 没 profile 的用户(刚注册)在这条路径上会不会炸?

#### `2c73f6a` — 头像上传
- `avatar_url` Pydantic validator 是否能挡住 SVG with `<script>` 的攻击?(`data:image/svg+xml` 是 image 但执行 JS)
- 200KB 上限是否足够(中文圈用户头像 photo 多)?
- 前端 canvas 压缩 — 有没有原图比 256×256 还小的 case 被无谓放大模糊?
- `<img src={data url}>` 渲染时的 CSP 是不是要管?

#### `bc67b32` — MBTI 默认不勾
- useEffect 同步 value=null 时不触发,**用户主动勾 unknown → 父 onChange(null) → useEffect 收到 value=null → 现在不动 unknown**。这个状态机有没有"两个 useEffect 互相触发"的死循环风险?
- 如果用户先勾 INFJ(父 state 变 "INFJ"),又取消其中一维(父 state 变 null),unknown 现在是 false,显示就是"未选 unknown,但 4 维不全",符合预期吗?

### 提交方式(B 没有代码改动,review 报告本身是产物)

```bash
git checkout -b chore/codex-review-batch-2026-05-13
git add docs/reviews/
git commit -m "$(cat <<'EOF'
chore(review): CodeX 首批 review · 2fb8809 / 2c73f6a / bc67b32

第一批接入项目时的 review pass,覆盖最近 3 个 Claude 直推 main 的 commit。
报告分别在 docs/reviews/ 下,每份按 AGENTS.md docs/codex-onboarding.md
的 Task B 格式。

verdict 汇总:
- 2fb8809: <verdict>
- 2c73f6a: <verdict>
- bc67b32: <verdict>

如有 blocker / 必修项,Claude 看完会决定 follow-up。
EOF
)"
git push -u origin chore/codex-review-batch-2026-05-13
gh pr create --title "CodeX review batch · 2fb8809 / 2c73f6a / bc67b32" \
  --body "首批 review pass。Claude 主审。@用户最终拍板 merge。"
```

---

## Task A · 写后端单测(B 完成后做)

### 范围

为 `apps/api/src/auth/` 模块写 pytest 单测。三批:

1. **`tests/test_auth_password.py`** — `hash_password` / `verify_password` 的边界
2. **`tests/test_auth_register_login.py`** — register / login endpoint 端到端(用 httpx AsyncClient)
3. **`tests/test_auth_me_profile.py`** — `/me` GET 和 `PUT /me/profile`(含 avatar_url validator)

### 技术要求

- **pytest-asyncio**,所有 test 都是 `async def`
- **DB**:用 in-memory SQLite + `aiosqlite`(简单);如果某个 test 真需要 pg 特性(JSONB / partial index)再用 `pytest-postgresql`,且明确注释
- **LLM 调用**:全部 mock,**不要**真调 DashScope — 用 `monkeypatch` 或 `unittest.mock.AsyncMock` 替 `llm_chat`
- **HTTP client**:用 `httpx.AsyncClient(transport=ASGITransport(app=app))`
- **session cookie**:用 `client.cookies.set()` 模拟登录态,不真正走 OAuth
- **fixture**:在 `tests/conftest.py` 里集中提供 `db_session` / `client` / `mock_user`

### 必覆盖的 test case 清单

#### `test_auth_password.py`
- `hash_password("abc")` 产出 bcrypt 格式串
- `verify_password("abc", hash)` 通过;`verify_password("wrong", hash)` 失败
- `verify_password(plain, None)` 返 False(不抛)
- 同明文两次 hash 出不同串(salt 随机)
- 超长输入(200 字符中文,utf-8 > 72 byte)能正确 hash + verify(测 sha256 预处理)
- 空字符串 `hash_password("")` 抛 ValueError

#### `test_auth_register_login.py`
- POST `/register` happy path → 201 + session cookie + UserMeResponse
- 同 username 第二次 register → 409
- username 不符合 `^[a-zA-Z0-9_]+$` → 422 (Pydantic 拦)
- password < 8 字符 → 422
- POST `/login` 正确用户名密码 → 200 + session cookie
- 错密码 / 不存在的用户都返 401(同一 detail,防枚举)
- 注册时带 nickname → DB 里有 UserProfile row;不带 nickname → 没 row
- register 后立刻 `/me` 拿到的 UserMeResponse 字段齐全(google_avatar_url 字段在 — 哪怕 null)

#### `test_auth_me_profile.py`
- GET `/me` 未登录 → 401
- GET `/me` 登录后 → 返回 user + profile
- PUT `/me/profile` 首次写 → 设置 `onboarded_at`
- PUT `/me/profile` 第二次写 → `onboarded_at` 不变
- avatar_url 是 `https://...` URL → 通过
- avatar_url 是 `data:image/jpeg;base64,...` → 通过
- avatar_url 是 `data:text/html,...` → 422(不是 image)
- avatar_url 是 `javascript:alert(1)` → 422(不是 http/data)
- avatar_url = 空字符串 → 通过(被 validator 转成 None)
- avatar_url 超过 200KB → 422

### 提交方式

每个 test 文件一个 commit。最后:

```bash
git checkout -b feat/codex-auth-tests
# ... 写 + commit ...
git push -u origin feat/codex-auth-tests
gh pr create --title "feat(tests): auth 模块单测" \
  --body "$(cat <<'EOF'
覆盖:
- test_auth_password.py · X 个 case
- test_auth_register_login.py · X 个 case
- test_auth_me_profile.py · X 个 case

CI 还没建,本地 \`pytest apps/api/tests/\` 全绿。

注意点(给 Claude review 用):
- ...

Claude 主审。@用户拍板 merge。
EOF
)"
```

---

## Task C · 扩写 mock 用户 portrait_body(等 A+B 完成后)

略,你 A+B 跑完用户会单独通知。

## Task D · 给 cold_start_seed 加 --verify(等 A+B 完成后)

略,同上。

---

## 协作纪律提醒

- PR 上 Claude 会给 review 评论,**你回复要在 PR 里完成**,不要单独发消息绕开
- 改动如果触到 prompt / IA / schema,**先 hold,问用户**
- 不确定的事用 `gh pr comment` 抛出来,不要自己假设
- review 用文字,不灌 emoji

—

有问题在 PR 描述里直接问。Welcome aboard.
