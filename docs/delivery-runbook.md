# CyberMOMO 交付流程

> 适用于个人开发 + Codex Agent 协作。Git 与已验收的 Railway 状态是 truth；Agent 记忆只是派生信息。

## 1. 开工前

1. 说明要解决的问题、不改什么、验收标准和风险等级。
2. 运行 `git status -sb` 并保留用户或其他 Agent 的现有改动。
3. 从最新 `origin/main` 建任务分支。当 main 不干净、并行任务或任务较长时使用 worktree；小且独立的任务不强制 worktree。

## 2. 风险分级

| 等级 | 范围 | 要求 |
|---|---|---|
| 低 | 文档、测试、不改行为的文案、只读脚本 | CI 全绿，用户确认后 merge |
| 中 | 普通 UI/API、性能、依赖、部署配置 | CI 全绿 + 人工 review + 部署后 smoke |
| 高 | 登录/OAuth、生产数据、migration、Agent/Summary 核心 Prompt、Voice Audit 写入、单轮/批量重跑、admin 权限 | 开工前确认；PR 中标记；merge/生产操作前再次人工确认；保留回滚路径 |

AI 可以 review 和给出 merge 建议，不 approve、不自行 merge。高风险生产操作不得由 CI 自动执行。

## 3. 本地验证

API：

```bash
cd apps/api
python -m pip install -r requirements-dev.txt
pytest tests/
```

Web：

```bash
cd apps/web
npm ci --no-audit --no-fund --ignore-scripts
npm run typecheck
npm run lint
NEXT_PUBLIC_DEV_MOCK_AUTH=false npm run build
```

只运行与变更相关的额外检查。基础 CI 不调用真实 LLM、Google 真实账号、Railway 生产数据库或生产 admin endpoint。

提交 `package-lock.json` 前检查 `resolved` 地址：仓库 lockfile 只能指向 `https://registry.npmjs.org/`，不得写入公司内网或个人 registry。

## 4. PR 与 merge

1. PR 描述必须包含边界、风险、验证证据、Railway 影响面、线上验收清单。
2. `pr-risk-gate`、`api-tests` 和 `web-checks` 是基础 required checks。PR 必须填写三项任务边界且只能选择一个风险等级；高风险确认不完整时不能合并。PR 描述被编辑时必须重跑 gate，避免检查通过后改变风险声明。
3. 默认 squash merge；禁止直接 push main。
4. 只有用户可以决定 merge。

GitHub `main` 必须保持以下保护：只允许 PR 合入、三项基础检查 required、分支必须最新、conversation 必须解决、线性历史、禁止 force push 和删除。个人仓库不增加 CODEOWNERS 或强制 approve 数量；它们不能替代用户对中高风险任务的判断。

## 5. Railway 部署

merge 后记录 merge commit、受影响服务、Railway deployment ID 与实际运行 commit。含 migration 的发布属于高风险，必须先确认兼容性、备份和回滚方案。

Railway watch paths 必须保持服务隔离：backend 与 observation cron 只因 `apps/api`、根 Dockerfile 或根 Railway 配置变化而部署，frontend 只因 `apps/web` 变化而部署。纯文档、GitHub workflow 和只读交付脚本不应触发业务服务重建。

读 Railway 配置时只查询需要的非敏感字段。禁止导出或打印整份 production variables/config，禁止在日志、PR、文档或 Agent 记忆中写入 secret。

## 6. 部署后正式验收

Railway 显示绿色不等于产品可用。至少验证：

1. `https://cybermomo-production.up.railway.app/healthz` 返回 200。
2. `https://cybermomo-app.up.railway.app/` 能打开并正常渲染。
3. frontend 同域 `/api/auth/me` 能连到 backend，未登录时返回预期 401。
4. 涉及用户路径时，用授权的测试账号验证实际页面行为。
5. OAuth 任务必须验证 Google 跳转、callback、session、登出和新旧用户落地页。
6. 对中国用户可用性有要求时，使用真实移动 4G/5G 再验收；不用 Railway service status 代替。

真实模型效果、Voice Audit 和生产数据验收只能作为按需工作流或人工验收，不作为基础 CI gate。

### 6.1 自动化只读 smoke

本地或 CI 均使用同一脚本：

```bash
python3 scripts/production_smoke.py --check-oauth-redirect
```

脚本只验证 backend health、frontend HTML、同域 `/api/auth/me` 和可选的 Google redirect/state cookie，不选择真实账号、不调用真实模型、不写生产数据。

merge 并确认 Railway 部署完成后，在 GitHub Actions 手动运行 `Production smoke`。输入受影响服务、Railway deployment ID 或 dashboard 证据引用；workflow summary 和 30 天 artifact 是该次发布的验收记录。脚本通过不等于 Railway commit 已匹配，运行人仍须先从 Railway 确认实际运行 commit。

### 6.2 必须人工的验收

- 登录/OAuth：真实账号 callback、session、登出、新旧用户落地页。
- Agent Chat/Summary/核心 Prompt：授权测试账号 + 真实模型质量。
- Voice Audit、单轮/批量重跑、生产数据/admin 写操作：动作前和执行前两次确认，并记录范围、恢复方案和结果。
- 中国移动网络：确有可用性要求时由真人使用 4G/5G 验证，并把结果写入 workflow input 或 PR。

## 7. Truth sync 与清理

验收通过后再同步 README、AGENTS.md、runbook 和必要的 Agent 记忆。记忆必须标明已验证的 commit/部署事实，不得包含 secret 或用户数据。

用户确认任务完成后，再删除远程/本地分支、worktree 和临时资源；高风险任务保留必要的验收和回滚记录。

## 8. 分阶段完成定义

- Phase 1：任务边界、风险分级、独立分支/worktree、PR template 和基础 CI 已落地。
- Phase 2：`main` 分支保护已启用，任务边界/风险 CI gate、required checks、人工 review、用户 merge 决策成为强制路径。
- Phase 3：部署后只读 smoke、Railway 证据记录、真实账号/模型/生产数据人工门禁、truth-sync 和确认后清理形成闭环。
