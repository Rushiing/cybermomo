# CyberMOMO

> AI 先行社交平台。**先聊的不是你**——让 Agent 替你做社交初筛,把真正有意思的人类还给人类。

## Monorepo 结构

```
cybermomo/
├── apps/
│   ├── api/              # FastAPI 后端(Python 3.11+)
│   └── web/              # Next.js 14 前端(TypeScript + Tailwind)
├── legacy/
│   └── prototype-v0.4/   # 盲测期 prototype(LLM 生成 .md)· 已 deprecated
├── scripts/              # 数据迁移、运维脚本
├── Dockerfile            # 后端 service 镜像构建(Railway 默认 service)
├── docker-compose.yml    # 本地 Postgres + pgvector
├── railway.json          # Railway 部署配置(指向 Dockerfile)
└── .env.example          # 环境变量示例
```

## 设计文档

完整设计文档在另一个 vault:`../cybermomo/`

- **PRD** · `cybermomo/PRD/PRD-CyberMOMO-v1.1.md`
- **工程架构** · `cybermomo/工程拆解/_工程架构.md`
- **数据模型** · `cybermomo/工程拆解/_数据模型.md`(15 张表)
- **交互设计** · `cybermomo/交互拆解/`(原则 / IA / 调性 / happy path)
- **HTML 原型** · `cybermomo/DEMO/mvp/`(13 屏 happy path 可点点点)

## 快速开始

```bash
# 1. 起本地数据库
docker-compose up -d

# 2. 后端
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env  # 填写
uvicorn main:app --reload --port 8787

# 3. 前端(另一个 terminal)
cd apps/web
pnpm install   # 或 npm i
pnpm dev       # http://localhost:3000

# 4. 验证
curl http://localhost:8787/healthz
```

## 部署

部署到 Railway。

- **service-api**:跑 `apps/api/`(本 repo 默认 service)
  - 域名:cybermomo 主域名(已绑定)
  - Postgres + pgvector 通过 Railway Postgres 插件提供
  - 配置 env(见 `.env.example`)
- **service-web**:跑 `apps/web/`(后续可选添加)
  - 也可部署到 Vercel(Next.js 原生友好)

## 历史

- `legacy/prototype-v0.4/` 是盲测期 prototype(LLM 生成 markdown 的 .md 创建路径),MVP 阶段已 deprecated。保留作为历史 + 数据迁移参考(盲测期收集的数据需要 cutover 时迁到新表)
- 当前 git remote 接管自盲测期项目;首次 monorepo 改造从 commit `fa43810` 之后开始

## Phase 进展

| Phase | 状态 |
|---|---|
| **Phase 0 · 地基** | ✅ 已落(monorepo + 15 表 schema + LLM 网关 + auth/md router skeleton + smoke test) |
| Phase 1 · 注册 + .md 创建 | 下一步:Google OAuth 接入 + POST /api/md 实装 |
| Phase 2 · 匹配 + Agent 互聊 | 待启动 |
| Phase 3 · 摘要 + 个人房间 | 待启动 |
| Phase 4 · 真人聊天 + callout + 观察报告 | 待启动 |
| Phase 5 · 联调 + 朋友盘内测 | 待启动 |

## 部署状态

- ✅ Railway 服务运行中,Dockerfile 构建,健康检查通
- ✅ Postgres + pgvector,15 张表创建(alembic init_v1)
- ✅ 每次 push 自动 `alembic upgrade head`(railway.json preDeployCommand)

## Phase 0 还可补的(P1,不阻塞 Phase 1)

- prompt seed 脚本(把 v0 prompts 抽出来塞进 prompt_versions 表,Phase 2 启用)
- Sentry 接入
- structured logging(目前用 print)
- 前端 service 部署(Railway 第二个 service 跑 apps/web/)
