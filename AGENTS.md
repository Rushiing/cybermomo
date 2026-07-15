# AGENTS.md

> 2026-07-15 起，本项目统一以 `AGENTS.md` 作为 Codex 主入口。`CLAUDE.md` 是指向本文件的兼容入口；新增规则只写这里。

> 给所有 AI 协作者(Claude / CodeX / 后来者)的 onboarding 文档。
> 这是项目级共识,你写代码前必读;commit message 也按这里的约定写。
> `CLAUDE.md` 是本文件的软链 — 改这一份两边同步。

---

## 1. 项目身份

**CyberMOMO** — AI 先行社交平台。"先聊的不是你" — Agent 替你做社交初筛,把真正有意思的人类还给人类。

- **阶段**:MVP 内测前最后冲刺(2026-05-13)
- **技术栈**:FastAPI(Python 3.11+ async)+ Next.js 14 App Router + Postgres 16 + pgvector + DashScope(OpenAI-compatible)LLM
- **部署**:Railway backend + frontend + Postgres + observation sweep cron

完整结构和本地启动看 `README.md`,不重复。

---

## 2. 当前节点(2026-07-15)

> 📍 **最新进展 + 无缝衔接,读 [`docs/handoff-2026-06-26.md`](docs/handoff-2026-06-26.md)** —— 本节是它的摘要。

**内测前加固(5 P0 全闭环)已全部完成、推上线、部署验证通过**(Batch 1 → 3.5b,codex 终审两轮判可上线)。现在在做"开真人内测前"的小 UX 打磨 + Rush 自己走 happy path 自测。

- backend 域名是 `https://cybermomo-production.up.railway.app`，frontend 正式域名是 `https://cybermomo.up.railway.app`。上线状态不在文档中固定写 commit；每次交付按 [`docs/delivery-runbook.md`](docs/delivery-runbook.md) 核对 GitHub merge commit、Railway 运行 commit 和正式域名行为。
- **内测 ops 三铁规矩 + 档 B 延后清单** 看 [`docs/beta-runbook.md`](docs/beta-runbook.md);审计报告看 [`docs/audit-2026-06.md`](docs/audit-2026-06.md)。

**下一步**:happy path 自测 → 开 ~100 人陆续进的真人内测;继续小 UX 打磨(已知待办:互聊回放话题标签还显示 `matchpoint_3` 这种内部 id,待换人话)。

> 冷启动 5 件事(2026-05-13)已全部合入,历史细节见 git log / 旧版本本节。

**不要碰的区域**(除非被明确指派):
- `legacy/prototype-v0.4/` — 盲测期遗弃代码,只读不动
- `apps/api/alembic/versions/` 已合并的 migration — 不可改,只能加新文件
- `apps/api/src/agent_chat/engine.py` / `summary/engine.py` 的 prompt 字符串 — Claude 主场,改前过用户

---

## 3. 平台铁律(7 条 · 必守)

违反任何一条都是产品事故,实现前先自问"这条会不会踩"。

### 3.1 · 平台底线 ≠ Agent 行为拉黑(数据隔离)
平台底线(黄赌毒/违法)必须**独立留底、不可撤销、不对用户暴露**;Agent 行为拉黑可撤销、用户可见。两类在 DB 必须分表/分字段,审计流水不能混。**禁止把平台底线写成"扩展自 Agent 拉黑"。**

### 3.2 · Agent 行为约束在平台 system prompt,不在 .md
所有 "Agent 必须/不能" 的硬规则放平台层 prompt(用户不可见不可改);`.md profile` 只承载人格描述、偏好、兴趣 — 不承载任何行为约束。判断标准:"如果用户编辑了 .md,能不能绕过这条?" 能 → 必须搬到平台层。

### 3.3 · Agent → 宿主的所有文案,统一"朋友式八卦"语气
摘要 / 简报 / callout / Agent 主动建议 / 错误提示(凡是 Agent 出面的) — 都是"替你出去社交的朋友回来跟你八卦"的口吻,不是系统消息。**只有支付失败、技术故障这种平台口吻消息**才不走 Agent 语气,且必须明确区分。Review 时问自己:"这像朋友回来跟你八卦吗?"

### 3.4 · `.md` 全文绝对不向他人暴露
用户的 `.md` 原文在**任何**面向他人的场景(广场 / 名片 / Agent 转述 / 真人聊天 / 搜索)都**绝对不全文出现**。只能暴露:
- 昵称
- 平台生成的脱敏摘要 / 关键词钩子(碎片化,不给全貌)
- Agent 基于 .md 的人格化表达(≠ 照搬原文)

设计任何"别人能看到的内容"前,先确认是否含 .md 原文 — 有 → 必须改脱敏形式。

### 3.5 · prompt 分层与改动权限
- 平台 system prompt → Claude 主场,改之前过用户
- 反"装"硬约束 + verdict 分布锚 + peer demographic block — 已经校准过,**别回退**
- 调用方拼 prompt block 而不是字符串拼接散在各处 — `src/shared/peer_prompt.py` 是范式

### 3.6 · 外部链接/仓库扔过来时,默认问的是它本身
用户给一个 GitHub repo + 模糊动词("看看 / 适不适用")时,**先按中立项目评估回答**(是什么、活跃度、技术亮点、缺点)。不要自动套到 CyberMOMO 上做对照表。除非用户明确点了那个方向。

### 3.7 · zero 人工干预原则不覆盖平台底线
产品的"零人工干预"是 Agent 社交那一层;平台底线是硬兜底,必要时人工介入留证(完整保留违规数据,不只是标记)。

---

## 4. 工程约定(踩过坑的,别再踩)

### 4.1 · 分支与发布

**所有 AI 协作工作流**:走 PR，不直推 main。
1. 一个任务一个分支(`feat/codex-add-auth-tests` / `chore/codex-review-2c73f6a` 这种命名)
2. push 分支后开 PR,标题 + 描述按本文档 §4.2 commit message 规范
3. **PR 主审是 Claude**(`gh pr review --comment`)— 找 bug、对边界、查 7 条铁律
4. Claude review 完产出一条 summary 评论(必修项 / 建议项 / OK 通过)
5. **merge 由用户拍板**,Claude 不点 approve,只给意见
6. merge 进 main 后,CodeX 删自己的分支

涉及第 3 章铁律的 PR,Claude review 至少要明确点过那条编号 — 用户能在 PR 评论里看到痕迹。

不动 prompt / IA / schema 不经过用户(无论谁动)。

跨 service 部署:api 在 repo root 的 `Dockerfile`,web 在 `apps/web/Dockerfile`,Railway 各拉各的。

### 4.2 · Commit message
- **必带"为什么"**,不只写"加了 X"
- 用中文,文末加 `Co-Authored-By:` 行(给下一个 AI 留信号)
- 拆 commit:一个 commit 一件事;不要把 "fix bug + refactor + add feature" 揉一起
- 范式参考 `git log` 最近 20 个

### 4.3 · AI 协作者身份(commit author)

每个 AI 协作者在自己的工作环境里跑一次:

**Claude**(直推 main):
```bash
git config user.name "xihe"
git config user.email "<用户的 git email>"
# Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
(Claude 不持有独立 git 身份 — author 是用户,Co-Author 标记 AI 协作)

**CodeX**(走 PR):
```bash
git config user.name "CodeX"
git config user.email "codex@cybermomo.local"
# Co-Authored-By: 不需要,身份本身就是 CodeX
```

这样 PR 列表里一眼区分"谁写的代码",方便 Claude 审查。

### 4.4 · Python / FastAPI
- 全异步 SQLAlchemy 2.0(`AsyncSession` + `selectinload`,**不要**触发 lazy load)
- pydantic v2(`field_validator` / `ConfigDict`)
- Alembic revision id **≤ 32 字符**(踩过坑,`alembic_version.version_num` 是 varchar(32))
- 数据库连接池 size=20 + overflow=20,pool_recycle=1800(Railway PG 会 NAT 断,别动)
- SSE 流式 endpoint 用"多 session"模式 — 流期间释放 DB 连接(`src/agent_self/engine.py::stream_and_persist` 是范式)

### 4.5 · 密码 / 认证
- bcrypt rounds=10(Railway shared CPU,12 会 1-2s;OWASP 2024 推荐下限 10)
- 用裸 `bcrypt` 库,**不要**回退到 `passlib`(已知和 bcrypt 4.1+ ABI 冲突 → worker crash)
- 密码先 sha256 + base64 预处理再丢 bcrypt(绕过 72-byte 限制)
- 失败响应统一 401,不区分 "用户不存在" vs "密码错"(防枚举)

### 4.6 · LLM 调用
- 统一走 `src/llm/gateway.py::llm_chat`(自带日志 + 失败重试 + role-based 模型路由)
- `_parse_loose_json` 容忍 LLM 偶尔吐 markdown 围栏
- 不要在 LLM 流期间持有 DB 连接 — 会把池子打死

### 4.7 · 前端
- Next.js 14 App Router,`"use client"` 显式标
- API 调用统一走 `lib/api.ts` 的 `api.get / api.post / api.put`(自动带 cookie + base URL)
- 流式 endpoint 用 `streamSSE` helper
- 设计 tokens 全部走 Tailwind config(`bg-bg-elevated` / `shadow-modal` 等,看 `tailwind.config.ts`)
- 上传图片走 client-side canvas 压缩 + data URL,**别**集成 R2/S3(MVP 阶段)

### 4.8 · 已踩过的雷
- migration revision id 太长 → varchar(32) 截断 → 部署崩
- 单 SessionLocal 并发 4 个 query → 池满
- passlib + bcrypt 4.1 → AttributeError → worker crash → connection reset
- `/me/page.tsx` chat_with_my_agent 当 decision 处理 → IA 错 → 重构

---

## 5. 目录主场

| 目录 | 主场 | 别的 AI 进入前 |
|---|---|---|
| `apps/api/src/agent_chat/` `summary/` `agent_self/` | Claude(prompt 工程) | 改 prompt 必须过用户 |
| `apps/api/src/auth/` | 共用 | 改 schema 过用户 |
| `apps/api/src/match/` `md/` | 共用 | — |
| `apps/api/alembic/` | 共用 | 新 migration 不动旧的 |
| `apps/api/tests/` | **CodeX 主场**(已建) | 新增行为优先补稳定、便宜、可重复的 test |
| `apps/web/components/` | 共用 | 设计 token 必须走 Tailwind config |
| `apps/web/app/` | 共用 | 整页改动过用户 |
| `scripts/` | 共用 | 写完即弃,不维护 |
| `legacy/` | **不动** | — |

---

## 6. 标准交付入口

- 任务边界、风险分级、分支/worktree、本地验证、PR、Railway 和线上验收统一按 [`docs/delivery-runbook.md`](docs/delivery-runbook.md) 执行。
- 低/中/高风险定义以 runbook 为准。登录/OAuth、生产数据、migration、Agent/Summary 核心 Prompt、Voice Audit 写入、单轮/批量重跑、admin 权限是高风险，必须人工确认。
- CI 只跑稳定、便宜、可重复的 API 测试和 Web 检查。真实模型、真实账号和生产数据验收不进基础 CI。

---

## 7. 协作纪律(给两个 AI 都看)

1. **commit message 是我俩之间唯一的留言板** — 写"为什么"不只写"做了什么"
2. **不动 prompt / IA / schema 不经过用户** — 这三类是产品边界
3. **不踩对方主场**(看 §5) — 如果非要改,commit message 里说明动机
4. **review 用文字,不用 emoji 灌水** — 找 bug 比赞美重要
5. **AI 不互相 approve** — Claude 可以 review CodeX 的 PR(给意见、提问、找 bug),
   但 **merge 必须用户点**;`gh pr review --approve` 不允许 AI 用
6. **信息流必须经过用户** — 不要 AI 之间私下"达成共识"绕开用户

---

## 8. 用户语气(对你写代码不重要,但能帮你预判)

- 偏好简短直接的中文,英文术语保留(commit / endpoint / migration)
- 不喜欢 emoji 灌水,但 commit / 文档里偶尔点缀 OK
- "推" = git push,自己手动跑(Claude 没权限)
- "推一下"语气 ≠ 推荐技术方案,而是要你推 git
- 重大决策一定等用户拍板,不要自己做主

---

_本文档维护者:Claude(主),CodeX 接入后共同维护。修改前在 commit message 里说明动机。_
