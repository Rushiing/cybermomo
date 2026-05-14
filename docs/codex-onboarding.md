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

## 第一批 A+B 完成情况(回放 · 2026-05-14)

PR 5(review)和 PR 6(auth tests)已合 main。Claude 在 PR 评论里留了完整 review,
落地了 3 个 follow-up commit:`4213a1d` / `6bebc7d` / `3267836`。

**这批做得好的地方**:
- PR 5 抓到 SVG data URL 安全漏洞,**Claude 没看到**,真 blocker
- PR 6 顺手把那个漏洞修了(schema MIME 白名单 + base64 validate)
- test 覆盖完整,SVG 拒绝 case 直接锁住 review 漏洞

**第二批要避免的事**(本次教训):
1. **不动 schema 不经过用户** — PR 6 顺手改了 schemas.py + router.py,虽然这次接受了,
   下次类似情况**先在 PR 评论 ping 一下**再动手。`AGENTS.md §4.1` 那条。
2. **brief 不准时主动问**,不要按可能错的 brief 写代码(/register 201 vs 200 那条
   是 Claude brief 写错,如果你提前问一句就少绕一圈)。

---

## Task C · 扩写 20 mock archetype 的 portrait_body

### 现状

`scripts/mock_user_archetypes.py` 里 8 个 archetype(A-H),每个 `_X_BASE` dict 的
`portrait_body` 字段是 `list[str]`,目前只有 2 句话,总字数 ~50 字。冷启动后这些
mock 用户会进入真人 onboarding 后的 matching 池,真人看到对方的 portrait 不够立体
就没法判断是不是想真聊。

### 你要做的

扩写每个 archetype 的 `portrait_body`,**只动这一个字段**,其他不动。

要求:
1. **保持 `list[str]` 结构** — 分 2-3 段(原来就是 2 段,可加一段不强求)
2. **总字数 80-120 字** — 不是每段 80 字,是整个 list 拼起来 80-120
3. **跟 demographic + dialogue 数值对齐**:
   - 比如 A 沉静观察者 `social_energy=25 / sharing_drive=78` → portrait 要体现
     "对外不主动,但聊到对的话题会突然话很多"
   - 比如 D 直率女将 `agency.task_initiation=88 / decision_assertiveness=90` → portrait
     体现"动手快、判断直接"
   - 数值我已经写好,你别动,你的活是把数值翻译成人话
4. **保持现有第二人称"你"调性** — 像 Agent 跟宿主描绘 TA 是谁,**不是**第三人称报告
5. **避免 AGENTS.md §3.3 提的"AI 装感"用语**(参考 `src/agent_chat/engine.py` 的反"装"
   硬约束):
   - 禁用 "总而言之 / 这位朋友 / 综合来看 / 不得不说"
   - 禁用 "非常 / 十分 / 真的太"
   - 鼓励:断句、口语、有棱角的判断("XX 你不太行")、半句话("...")

### 边界

- **不引入新字段** — 不要顺手加 portrait_tags 长度、不要加 demographic 字段
- **不改 dialogue/boundary 数值** — 数值是 Claude 设计的人格锚,改了 portrait 会脱节
- **variant 之间可以差异化**(比如 A 的 3 个 variant 用不同侧重)但保持骨架性格一致
- **portrait_title 不动** — 那是已经定的人格标题

### 跑一次确认没坏

```bash
cd /path/to/cybermomo-app
python3 scripts/mock_user_archetypes.py
```

这个脚本独立可执行,会打印 20 人摘要 + 校验 profile 能构造。你跑出来 20 行齐全 + 没
exception 就 OK。

### 提交方式

```bash
git checkout -b feat/codex-portrait-bodies
# 改 scripts/mock_user_archetypes.py(只这一个文件)
git add scripts/mock_user_archetypes.py
git commit -m "$(cat <<'EOF'
feat(seed): 扩写 20 mock archetype 的 portrait_body 到 80-120 字

冷启动 mock 用户的 portrait 之前只有 2 句话约 50 字,真人 onboarding 后看
matching 池时不够立体。本 commit 在不改 demographic / dialogue 数值的前提下,
把每个 archetype 的 portrait_body 翻译成 80-120 字的人话。

调性:第二人称、口语、避免"AI 装感"用语(对齐 AGENTS.md §3.3 + agent_chat
engine 的反装约束)。variant 之间在共同人格锚下做侧重差异。

Co-Authored-By: 不需要
EOF
)"
git push -u origin feat/codex-portrait-bodies
gh pr create --title "feat(seed): 扩写 20 mock archetype portrait_body" \
  --body "覆盖 8 archetype × 2-3 variant = 20 人。
不改 demographic / dialogue 数值。
本地 \`python3 scripts/mock_user_archetypes.py\` 跑通,20 行齐。

Claude 主审。@用户拍板 merge。"
```

---

## Task D · 给 cold_start_seed 加 `--verify` 子命令

### 现状

`scripts/cold_start_seed.py` 跑完只能 `psql` 进 DB 手 SELECT 看效果。冷启动后要看
- 20 个 mock 用户是不是都进库了
- agent_chat 跑了多少场(预期 30-40 对)
- summary verdict 分布对不对(`AGENTS.md §3.5` 校准过的目标:来电 ~30% / 再观察 ~50% / 不合 ~20%)

### 你要做的

加 `--verify` 子命令(argparse,不要换 click)。调用方式:

```bash
cd apps/api
DATABASE_URL=... PYTHONPATH=. python3 ../../scripts/cold_start_seed.py --verify
```

期望输出格式(参考,具体数字不强求):

```
=== Mock Pool Verification ===
Mock users (is_system_mock=true): 20
  by archetype: A=3, B=3, C=3, D=3, E=2, F=2, G=2, H=2
  by gender: female=10, male=8, non_binary=2
  by age_band: 18-25=4, 25-30=6, 30-35=5, 35-40=3, 40+=2

=== Agent Chats ===
Total chats involving mock users: 35
  done_natural: 28 (80%)
  done_terminated: 5 (14%)
  running: 2 (6%)  ← 异常,提示用户检查
  end_reason 分布: natural_wrap=23, turn_limit=5, boundary_hit_铁律=2, ...

=== Summaries ===
Total summaries involving mock users: 70
  verdict 来电: 18 (26%)  ← target ~30%
  verdict 有点意思再观察: 38 (54%)  ← target ~50%
  verdict 不合: 14 (20%)  ← target ~20%

=== Health ===
✓ Mock count matches archetypes (20)
⚠ 2 chats still running (重跑过没?)
✓ Verdict distribution within tolerance(±10%)
```

### 实现要求

1. **只读** — 不动 seed 主流程,不写库
2. **argparse** — `--verify` 跟现有的 `DRY_RUN` / `SKIP_PIPELINE` 环境变量并存,
   `--verify` 是新增 flag,带这个就只跑 verification 不跑 seed
3. **复用现有 SessionLocal** — 不要再起新的 engine
4. **SQL 用 SQLAlchemy 表达式 + func.count** — 不要拼 raw SQL
5. **archetype 分组**:`username LIKE 'mock_xxx_a%'` 来识别 archetype(看 fixture
   命名约定 `mock_<name>_<letter><n>`)
6. **冷启动后跑得动 = 通过** — 不要求 unit test,但请人工跑一次确认输出对

### 边界

- **退出码** — verify 即使发现异常也只是 print,**返 0**;不要因为 verdict 偏差就 exit 1
- **不引入新依赖** — argparse 是 stdlib
- **mock 用户判定** — 一律用 `User.is_system_mock == True`,不要用 username 前缀
  (前缀只用来分 archetype)

### 提交方式

```bash
git checkout -b feat/codex-seed-verify
# 改 scripts/cold_start_seed.py
git add scripts/cold_start_seed.py
git commit -m "feat(seed): cold_start_seed 加 --verify 子命令"
git push -u origin feat/codex-seed-verify
gh pr create --title "feat(seed): cold_start_seed --verify" \
  --body "新增 verification 子命令,只读输出 mock pool + agent_chat + summary
verdict 分布。冷启动后用来确认 prompt 校准效果。

Claude 主审。@用户拍板 merge。"
```

---

## 后续 batch

C+D 完成后,用户会决定下一批。可能方向:
- 给 `apps/web` 补 E2E test(Playwright)
- 给 `src/agent_chat` / `summary` 模块写单测(LLM 全部 mock,锁 prompt 行为)
- 把 `seed_demo_users.py` 老脚本整合进 `cold_start_seed.py`(技术债)

---

## 协作纪律提醒

- PR 上 Claude 会给 review 评论,**你回复要在 PR 里完成**,不要单独发消息绕开
- 改动如果触到 prompt / IA / schema,**先 hold,问用户**
- 不确定的事用 `gh pr comment` 抛出来,不要自己假设
- review 用文字,不灌 emoji

—

有问题在 PR 描述里直接问。Welcome aboard.
