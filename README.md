# CyberMOMO

> AI 先行社交平台。**先聊的不是你**——让 Agent 替你做社交初筛,把真正有意思的人类还给人类。

## Monorepo 结构

```
cybermomo/
├── apps/
│   ├── api/              # FastAPI 后端(Python 3.11+)
│   │   ├── alembic/      # 数据库迁移
│   │   ├── src/          # 业务模块(auth/md/match/agent_chat/...)
│   │   └── Dockerfile    # api service 镜像
│   └── web/              # Next.js 14 前端(TypeScript + Tailwind)
│       ├── app/          # App Router 页面
│       ├── components/   # 共享组件
│       ├── lib/          # API client + v3 题库 + 规则引擎
│       └── Dockerfile    # web service 镜像
├── legacy/
│   └── prototype-v0.4/   # 盲测期 prototype(已 deprecated)
├── scripts/              # 数据迁移 / 运维 / demo seeder
├── Dockerfile            # api service(根目录默认 service)
├── docker-compose.yml    # 本地 Postgres + pgvector
├── railway.json          # api service 部署配置
└── .env.example          # 环境变量示例
```

## 设计文档(在另一个 vault)

- **PRD** · `cybermomo/PRD/PRD-CyberMOMO-v1.1.md`
- **工程架构** · `cybermomo/工程拆解/_工程架构.md`
- **数据模型** · `cybermomo/工程拆解/_数据模型.md`(15 张表)
- **交互设计** · `cybermomo/交互拆解/`(原则 / IA / 调性 / happy path)
- **HTML 原型** · `cybermomo/DEMO/mvp/`(13 屏 happy path)

## 快速开始(本地)

```bash
# 1. 起本地 DB
docker-compose up -d

# 2. 后端
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env   # 填写 GLM_API_KEY / ANTHROPIC_API_KEY 等
alembic upgrade head
uvicorn main:app --reload --port 8787

# 3. 前端(另一个 terminal)
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8787 npm run dev

# 4. 验证
curl http://localhost:8787/healthz
open http://localhost:3000
```

## 部署到 Railway

### service-api(默认 service · 后端)
- Root Directory: `(repo root)`
- Builder: Dockerfile
- Postgres 插件:自动注入 `DATABASE_URL`(代码会自动归一为 asyncpg 格式)
- 容器启动时先运行 `alembic upgrade head`
- 必填 Variables:`GLM_API_KEY` / `ANTHROPIC_API_KEY` / `JWT_SECRET` / `CORS_ORIGINS` / `ADMIN_SECRET`
- Google OAuth:`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URI=https://<web 域名>/api/auth/google/callback` / `WEB_BASE_URL=https://<web 域名>`

### service-web(独立 service · 前端)
- Root Directory: `apps/web`
- Builder: Dockerfile
- 必填 Variables:`NEXT_PUBLIC_API_URL=https://<api 域名>`
- 生产不要设置 `NEXT_PUBLIC_API_CLIENT_BASE`;浏览器走 web 同域 `/api`，由 Next rewrites 代理到 api service

### Cron Job(可选 · 每小时跑 24h 沉默 sweep)
```
curl -X POST -H "X-Admin-Secret: $ADMIN_SECRET" \
     https://<api 域名>/api/admin/observation-sweep
```

## API 概览

```
注册 / 我          GET /api/auth/me / PUT /api/auth/me/profile
.md 创建           POST /api/md(自动触发 pipeline)/ GET /api/md/me
匹配               POST /api/match/run / GET /api/match/me
简报               GET / 单个 / 决策 /api/summary/{me,id,id/decision}
个人房间           GET /api/room/status / blocklist 管理
真人聊天           POST /api/chat/sessions/from-summary/{summaryId}
                   GET / POST messages / callout / briefing / exit
Admin(cron 调)   POST /api/admin/observation-sweep
                   POST /api/admin/rerun-pipeline/{user_id}
```

## 完整 pipeline(POST /api/md 自动触发)

```
matching engine      → matches + matchpoints (纯 compute,无 LLM)
desensitize Agent    → match_hooks(GLM-5)
agent_chat engine    → agent_chat_messages(GLM-5,< 12 轮)
summary Agent        → summaries(Claude · 给两位 host 各一份)
```

真人聊天链路(用户决策开聊后):
```
prebriefing Agent    → §4.9 简报(Claude)
chat_session         → 双方真人 messages
callout Agent        → 私有 callout(Claude · host 不可见对方)
exit / 24h 沉默       → observation Agent → 观察报告(Claude)
```

## 测试 / Seeder

```bash
# 稳定的基础验证（不调真实 LLM）
cd apps/api && python -m pip install -r requirements-dev.txt && pytest tests/
cd apps/web && npm ci && npm run typecheck && npm run lint && npm run build

# 一键创建 3 个差异化 mock 用户(自动触发 pipeline)
python scripts/seed_demo_users.py

# 自定义 user_id + API
USER_IDS=10,11,12 API_URL=http://localhost:8787 python scripts/seed_demo_users.py

# 手动 curl 测
curl -H "X-Mock-User-Id: 1" https://<api 域名>/api/summary/me
```

## Phase 进展

| Phase | 状态 |
|---|---|
| **Phase 0 · 地基** | ✅ monorepo + 15 表 schema + LLM 网关 + Sentry + admin sweep |
| **Phase 1 · 注册 + .md 创建** | ✅ 后端实装(mock auth)+ 前端 onboarding/basic/quiz/review |
| **Phase 2 · 匹配 + Agent 互聊** | ✅ matching engine(纯 compute)+ desensitize + agent_chat turn engine |
| **Phase 3 · 摘要 + 个人房间** | ✅ summary Agent + room endpoints + 简报卡决策 |
| **Phase 4 · 真人聊天 + callout + 观察** | ✅ prebriefing + chat session + callout drawer + observation |
| **Phase 5 · 朋友盘内测** | 进行中 |

## 还没做(都不阻塞 MVP 内测)

- **Prompt 入 prompt_versions 表**(目前 inline Python 字符串,后续 PE 阶段改 DB 驱动)
- **图片上传**(真人聊天 content_type=image 暂时只能传 URL)
- **structured logging**(目前 print)
- **rate limiting / cost cap**

## 历史

- `legacy/prototype-v0.4/` 是盲测期 prototype(LLM 生成 markdown 的 .md 创建)。MVP 已切换为 v3 规则引擎。
- 当前 git remote 接管自盲测期项目;monorepo 改造从 commit `fa43810` 之后开始
