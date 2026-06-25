# CodeX Onboarding · 第一批任务(2026-05-13)

> 欢迎接入 CyberMOMO 项目。先看 [`AGENTS.md`](../AGENTS.md) 全文,这里是你第一批要做的活的详细 brief。
>
> 完成顺序:**先 B 后 A**(B 是 review 工作能让你先读懂代码再动手写测试)。

---

## 前置准备(只跑一次)

### 1. 配 git 身份(commit author)

```bash
cd /path/to/cybermomo/app
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
cd /path/to/cybermomo/app
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

---

## Task E · prompt 工程 + 平台铁律的 test 安全网

### 背景

冷启动 5 件事已经做完(prompt 校准 + peer demographic 注入 + 双轨认证 + mock seed)。
但**prompt 工程 + 平台铁律相关的代码完全没 test 覆盖**,真人内测开始后任何回归都
不好排查。Claude 评估后判断:**这块 ROI 最高,真出事比补测试贵 10x**。

不让 CodeX 测的(已划出去):
- LLM 真实输出质量(只能人工跑)
- Playwright E2E(后续 batch)
- match 算法(优先级低)
- prompt 字符串完整 snapshot(脆弱,改 prompt 就重 snapshot)— **只断言关键短语存在**

### 拆 2 个 PR

#### **PR E1** — 纯函数 / 数据校验(高 ROI,无 LLM 依赖)

| 文件 | 范围 | 优先级 |
|---|---|---|
| `tests/test_peer_prompt.py` | `format_peer_block` 5 gender × age 组合 | 🔥 最高 |
| `tests/test_desensitize.py` | hook 输出**不含** .md 原文(§3.4 硬墙) | 🔥 最高 |

#### **PR E2** — LLM mock(共用 fixture)

| 文件 | 范围 | 优先级 |
|---|---|---|
| `tests/test_agent_chat_prompts.py` | PLATFORM_SYSTEM + TURN_PROMPT + direction_hint 注入 | 高 |
| `tests/test_summary_prompts.py` | SUMMARY_SYSTEM 含 verdict 分布锚 + 双 host 简报 | 高 |
| `tests/test_agent_self_peer_resolver.py` | 3 种 scope 解 peer_user_id | 中 |

---

### PR E1 · 详细 brief

#### `tests/test_peer_prompt.py`

测 `src/shared/peer_prompt.py::format_peer_block`(纯函数)。**这是回归保护**:
确保"对方女不被叫哥们儿 / 非二元不带性别词 / 跨年龄段不用同辈词"这些硬约束不被
后续改 prompt 时无意中破坏。

必覆盖 case(对照 `peer_prompt.py` 现有 5 个分支):

1. **female 同龄**:`peer_gender="female", peer_age="25-30", host_age="25-30"` →
   输出包含**字面字符串**`"禁用"`和 `"哥们儿"`,不含 `"姐妹"` 之前的反义词。

2. **male 同龄**:`male / 25-30 / 25-30` → 输出含 `"可以用'哥们儿"`,不含 `"禁用"`。

3. **male 跨年龄段**:`male / 40+ / 18-25` → 输出含 `"跨年龄段"`,**不能**含 "可以用'哥们儿"。

4. **non_binary**:`non_binary / 30-35` → 输出含 `"@nickname"` 或 `"TA"`,**不能**
   含 "哥们儿 / 姐妹 / 兄弟" 任一(用 `assert all(w not in result for w in ...)`)。

5. **prefer_not_to_say**:输出走"默认走 @nickname"分支。

6. **全 NULL 字段**:`peer_nickname=None, peer_age=None, peer_gender=None` →
   输出含 `"NULL 字段多"` 或回退 `"user_X"`。

7. **nickname=None 但 peer_user_id 有值**:输出含 `"user_<id>"` 占位。

8. **peer_mbti 是 None**:不应 raise,且输出里不出现 "MBTI:"。

9. **跨年龄段判定边界**:差 2 档(`18-25` vs `30-35`)算跨年龄段,差 1 档(`25-30` vs `30-35`)
   不算。可以用 `_age_gap_is_large` 间接测,但更稳是断言 format 输出关键短语。

10. **mbti = None 且 peer_user_id 有值**:不崩,输出不含 "MBTI:" 行。

**实现要求**:
- **不需要 DB / async** — 纯函数测试,用 `def` 不用 `async def`
- 断言**关键字面字符串存在 / 不存在**,不要做整段 snapshot 比对(脆弱)
- 输出全部 print 一下方便人工目视检查

#### `tests/test_desensitize.py`

测 `src/match/desensitize.py` 的**铁律级**保护:hook 输出不能包含 .md 原文。

这是 **§3.4 平台铁律**对应的硬墙 — 用户原话:"这个暴露,太吓人了,跟直接大街上脱了别人衣服似的"。

必覆盖 case:

1. **`_extract_safe_profile_summary` 不暴露 raw_answers**:
   - 构造一个含 `raw_answers = {"E1": {"option_text": "我喜欢深夜独自读小说"}}` 的 profile
   - 跑 `_extract_safe_profile_summary(profile)` → assert 返回的 dict 序列化成 json 后**不含** "深夜独自读小说"
   - 跑 `_bucketize_dimensions` 同样断言

2. **`_extract_safe_profile_summary` 不暴露 portrait.body 原文**:
   - profile 含 `portrait.body = ["你是个慢热但深度的人"]`
   - 返回 dict 不含 "慢热但深度"

3. **`_bucketize_dimensions` 数值正确分档**:
   - `dialogue.social_energy = 80` → "高"
   - `social_energy = 50` → "中"
   - `social_energy = 20` → "低"
   - 边界:`67` → "高",`66` → "中",`34` → "低",`35` → "中"

4. **`_bucketize_dimensions` 跳过 None 值**:
   - profile 含 `dialogue.sharing_drive = None` → 输出 dict 不含 sharing_drive 键

5. **`_parse_loose_json` 容忍 markdown 围栏**:
   - 输入 ` ```json\n{"x":1}\n``` ` → 返回 `{"x": 1}`
   - 输入 `{"x":1}` 不带围栏 → 也能解析
   - 输入 `garbage` → 返回 `None`(不抛)

6. **`run_desensitize_for_match` 端到端**(LLM mock):
   - 构造 fake Match + Matchpoint + 双方 MdDocument
   - mock `llm_chat` 返回固定 JSON(含 hooks_for_a + hooks_for_b)
   - 跑完后断言 DB 里写入了 MatchHook 行
   - **关键断言**:写入的 hook_text 不含 profile_json 里 raw_answers 任何 option_text 字面
     (用 substring 比对,失败时打印是哪个 hook 漏了哪段 .md 原文)

7. **LLM 返回非法 JSON 时优雅退化**:
   - mock 返回 `"this is not json"` → `run_desensitize_for_match` 不抛,
     只是 `match.status` 标 desensitize_failed 或类似(看实现)

**实现要求**:
- 用 conftest 里现成的 SQLite + ASGI fixture
- LLM mock 用 `monkeypatch.setattr("src.match.desensitize.llm_chat", ...)`
- 测 §3.4 那条**字面 substring 比对**是核心,必须有

#### PR E1 提交方式

```bash
git checkout -b feat/codex-prompt-test-net-e1
# 写 tests/test_peer_prompt.py + tests/test_desensitize.py
pytest tests/test_peer_prompt.py tests/test_desensitize.py  # 本地跑过
git add apps/api/tests/test_peer_prompt.py apps/api/tests/test_desensitize.py
git commit -m "feat(tests): peer_prompt + desensitize 安全网"
git push -u origin feat/codex-prompt-test-net-e1
gh pr create --title "feat(tests): peer_prompt 5 称呼锚 + desensitize §3.4 铁律硬墙" \
  --body "PR E1 of 2 · 纯函数 / 数据校验,无 LLM 真调用。
  
覆盖:
- peer_prompt: <X> case,锁住 5 gender × age 称呼锚 + NULL 降级
- desensitize: <Y> case,核心是 hook_text **不含 .md raw_answers 字面** 的 substring 比对

下一个 PR E2 会覆盖 agent_chat / summary / agent_self prompt 渲染。

Claude 主审。@用户拍板 merge。"
```

---

### PR E2 · 详细 brief(E1 合完再开)

#### `tests/test_agent_chat_prompts.py`

测 `src/agent_chat/engine.py` 的 prompt 拼装 + LLM 调用边界。不验证 LLM 输出质量,
只验证**我们传给 LLM 的 prompt 包含该有的关键短语 + 不该回退的硬约束还在**。

必覆盖 case:

1. **PLATFORM_SYSTEM 含反"装"硬约束关键短语**:
   - 包含 `"禁用开场套话"` / `"禁用结尾甩问"` / `"禁用 AI 客气助词"`
   - 包含 `"真人审"` / `"两个 AI 在客气地互相恭维"`
   - 不含 `"很高兴认识你"`(防误把禁用词塞反方向)

2. **TURN_PROMPT_TEMPLATE 渲染后含 peer_block**:
   - mock `format_peer_block` 返 `"<MOCK_PEER_BLOCK>"`
   - 跑一轮拼 prompt → assert prompt 里有 `"<MOCK_PEER_BLOCK>"`

3. **`run_agent_chat` direction_hint 只注入 target_user_id 那一侧**:
   - mock `llm_chat` 拿到 prompt 后写入 list,后断言
   - turn 1(user_a)有 direction → prompt 含 `"宿主新方向指示"`
   - turn 2(user_b)无 direction → prompt 不含
   - direction_target_user_id 切换 → 注入方向反过来

4. **`avoid_topic_refs` 拼进 AVOID_BLOCK_TEMPLATE**:
   - 传 `["topic_a", "topic_b"]` → prompt 含 `"再派一次"` + `"topic_a"` + `"topic_b"`
   - 不传 → prompt 不含 `"再派一次"`

5. **LLM 返回 boundary_hit='铁律' → end_reason='boundary_hit_铁律'**:
   - mock 让第 1 轮返回 `{"private_signals":{"boundary_hit":"铁律"},...}`
   - 跑完 chat.status == "done_terminated" + end_reason 含 "铁律"

6. **双方连续 wrap → done_natural**:
   - mock 第 3、4 轮都返回 `intent="wrap"` → chat.end_reason == "natural_wrap"

7. **没 hooks 直接终止**:
   - 不创建 MatchHook → chat.status="done_terminated", end_reason="no_hooks"

8. **缺一方 profile → 终止**:
   - 只创建一方 MdDocument → end_reason="missing_profile"

**实现要求**:
- LLM mock 用 `monkeypatch.setattr("src.agent_chat.engine.llm_chat", ...)`
- mock 的 llm_chat 用 `AsyncMock`,返回固定结构(注意 `resp.text` 字段)
- fixture 帮忙构造 Match + MatchHook + 双方 MdDocument + UserProfile,
  考虑放 `tests/conftest.py` 共用

#### `tests/test_summary_prompts.py`

测 `src/summary/engine.py`:

1. **SUMMARY_SYSTEM_TEMPLATE 含 verdict 分布锚**:
   - 渲染后 prompt 含 `"来电(约 30%)"` / `"有点意思再观察(约 50%)"` / `"不合(约 20%)"`
   - 含 `"礼貌性回应"` + `"不算来电"`
   - 含 `"private_signals"` 提示看 warmth_delta 走势

2. **`run_summary_for_chat` 双 host 各产一份 summary**:
   - mock llm_chat 返合法 JSON
   - 跑完 DB 里有 2 行 Summary,host_user_id 一个 a 一个 b

3. **verdict 不在三档 → fallback "有点意思再观察"**:
   - mock 返 `{"verdict":"非常喜欢",...}` → DB 里写的是 "有点意思再观察"

4. **recommended_action 不在三档 → fallback "再派一次"**:
   - mock 返 `{"recommended_action":"立即结婚",...}` → DB 写 "再派一次"

5. **peer_block 被注入 SYSTEM**:
   - mock format_peer_block 返 `"<MOCK_PEER>"` → SYSTEM prompt 含

6. **空 messages → 跳过(返空 list)**:
   - 没创建 AgentChatMessage → run_summary_for_chat 返 `[]`

7. **LLM 抛错 → 跳过该 host 不影响另一个**:
   - mock 第一次抛 Exception,第二次正常 → DB 只有 1 个 Summary,不抛到上游

#### `tests/test_agent_self_peer_resolver.py`

测 `src/agent_self/engine.py::_resolve_peer_user_id` + `_load_peer_block`:

1. **scope='general' → None**

2. **scope='revisit' + context_refs={"peer_user_id": 5} → 5**

3. **scope='plaza' + context_refs={"target_user_id": 8} → 8**

4. **scope='room' + context_refs={"agent_chat_id": 99}**:
   - 构造 AgentChat(id=99, match_id=42) + Match(id=42, user_a=1, user_b=2)
   - conversation.host_user_id = 1 → 返回 2
   - conversation.host_user_id = 2 → 返回 1

5. **scope='room' 但 agent_chat_id 不存在 → None**(不抛)

6. **scope='room' 但 Match 被删 → None**(不抛)

7. **`_load_peer_block` 整合测试**:
   - 上面 scenario 4 → 调用 format_peer_block 时正确传入 peer 的 UserProfile

#### PR E2 提交方式

```bash
git checkout -b feat/codex-prompt-test-net-e2
# 写 3 个 test 文件
pytest tests/test_agent_chat_prompts.py tests/test_summary_prompts.py tests/test_agent_self_peer_resolver.py
git add apps/api/tests/test_agent_chat_prompts.py apps/api/tests/test_summary_prompts.py apps/api/tests/test_agent_self_peer_resolver.py
git commit -m "feat(tests): agent_chat / summary / agent_self prompt 渲染安全网"
git push -u origin feat/codex-prompt-test-net-e2
gh pr create --title "feat(tests): prompt 渲染 + scope peer resolver" \
  --body "PR E2 of 2 · LLM mock,只测我们传给 LLM 的 prompt 内容。

覆盖:
- agent_chat: PLATFORM_SYSTEM 反装短语 + TURN peer_block 注入 + direction_hint 单向
- summary: SUMMARY 分布锚 + 双 host 产出 + verdict fallback
- agent_self: 3 种 scope 解 peer + room scope JOIN chat→match

Claude 主审。@用户拍板 merge。"
```

---

### 共用注意点

**SQL fixture 扩展**:目前 `tests/conftest.py` 只 create 了 `User / UserProfile` 表。
E1 / E2 需要扩展支持 `MdDocument / Match / MatchHook / Matchpoint / AgentChat /
AgentChatMessage / Summary / AgentConversation`。建议:
1. 在 `conftest.py` 的 `session_factory` fixture 里**集中**追加所有需要的表
2. JSONB / Vector 字段在 SQLite 上可能炸 — JSONB 自动降级成 SQLite JSON 通常 OK,
   但 pgvector 的 `Vector(1024)` 在 SQLite 没驱动 → 如果遇到这种,改用 mock 或
   `pytest.importorskip("psycopg2")` skip 该 test。**遇到再说,不要提前加复杂度**

**LLM mock 范式**:
```python
from unittest.mock import AsyncMock

class FakeLLMResp:
    def __init__(self, text: str):
        self.text = text

monkeypatch.setattr(
    "src.agent_chat.engine.llm_chat",
    AsyncMock(return_value=FakeLLMResp('{"intent":"share",...}')),
)
```

**断言风格**:
- ✓ `assert "禁用开场套话" in system_prompt`
- ✓ `assert all(banned not in result for banned in ["哥们儿", "兄弟", "姐妹"])`
- ✗ `assert system_prompt == expected_full_string`(脆弱,改 prompt 就重写)

**字面短语清单**(给 CodeX 用来 grep 当前 prompt):

agent_chat PLATFORM_SYSTEM 必含:
- `"反"装"硬约束"` / `"禁用开场套话"` / `"禁用结尾甩问"` / `"禁用 AI 客气助词"`
- `"打断、跳话题、半句话"` / `"两个 AI 在客气地互相恭维"`

summary SUMMARY_SYSTEM 必含:
- `"verdict 分布参考"` / `"来电(约 30%)"` / `"有点意思再观察(约 50%)"` / `"不合(约 20%)"`
- `"礼貌性回应"` / `"不算来电"`

agent_self PLATFORM_SYSTEM_BASE 必含:
- `"朋友式八卦关系"` / `"参谋"` / `"执行键在宿主手上"`

---

## 后续 batch

E1 + E2 完成后可能方向:
- 给 `apps/web` 补 E2E test(Playwright,大改动单独 batch)
- 把 `seed_demo_users.py` 老脚本整合进 `cold_start_seed.py`(技术债)
- 实现一些遗留 follow-up(google_name 字段重命名为 display_name 等)

---

## 协作纪律提醒

- PR 上 Claude 会给 review 评论,**你回复要在 PR 里完成**,不要单独发消息绕开
- 改动如果触到 prompt / IA / schema,**先 hold,问用户**(上批教训)
- brief 不准时主动问,不要按可能错的 brief 闷头写(上批教训)
- 不确定的事用 `gh pr comment` 抛出来,不要自己假设
- review 用文字,不灌 emoji

—

有问题在 PR 描述里直接问。Welcome aboard.
