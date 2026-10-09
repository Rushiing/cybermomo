# CyberMOMO 交付流程

> 适用于个人开发 + Codex Agent 协作。Git、实际运行镜像与已验收的阿里云入口是 truth；Agent 记忆只是派生信息。

## 1. 开工前

1. 说明要解决的问题、不改什么、验收标准和风险等级。
2. 运行 `git status -sb` 并保留用户或其他 Agent 的现有改动。
3. 从最新 `origin/main` 建任务分支。当 main 不干净、并行任务或任务较长时使用 worktree；小且独立的任务不强制 worktree。

## 2. 风险分级

| 等级 | 范围 | 要求 |
|---|---|---|
| 低 | 文档、测试、不改行为的文案、只读脚本 | CI 全绿，在已授权交付范围内 merge |
| 中 | 普通 UI/API、性能、依赖、部署配置 | CI 全绿 + review + 已授权部署后的 smoke |
| 高 | 登录/OAuth、生产数据、migration、Agent/Summary 核心 Prompt、Voice Audit 写入、单轮/批量重跑、admin 权限 | 开工前确认；PR 中标记；merge/生产操作须有覆盖具体动作的用户授权；同一授权不重复申请；保留回滚路径 |

PR 不限定 Claude 主审；AI 可在用户授权范围内 review 和执行 merge，无需用户亲自点击。高风险生产操作不得由 CI 自动执行。

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
4. 用户授权持续有效，范围未变时可由 Agent 执行 merge；不得将局部修复擅自扩大为合并或生产发布。

GitHub `main` 必须保持以下保护：只允许 PR 合入、三项基础检查 required、分支必须最新、conversation 必须解决、线性历史、禁止 force push 和删除。个人仓库不增加 CODEOWNERS 或强制 approve 数量；它们不能替代用户对中高风险任务的判断。

## 5. 阿里云部署

以 `deploy/aliyun/PRODUCTION-20261009.md` 和实际运行配置为准。生产位于 Pre-RICH `/opt/cybermomo-prod`，Compose 项目 `cybermomo-prod`；模型与邮件凭据仅在私有环境文件中。记录代码版本、镜像 ID、迁移和回滚材料，不把 merge 当成 deploy。

仅在明确授权的发布范围内更新生产；重建 backend 后重启 frontend 刷新代理连接。保留 QuestionOS、NewRICH、Caddy 其他路由。旧 Railway 应用和发布触发器已停止；恢复旧站必须先处理切换后的新写入，不能直接打开旧库。

## 6. 部署后正式验收

分别验证容器健康、正式 HTTPS、同域匿名鉴权 401，再验证授权账号的登录/刷新/历史与本次受影响路径。Google 跳转成功不等于国内 OAuth 可用。真实模型和移动网络按实际测试范围报告。

### 6.1 现有只读 smoke 的执行位置

在 Pre-RICH 上运行仓库脚本，明确覆盖旧 Railway 默认值：

```bash
python3 scripts/production_smoke.py \
  --frontend-url https://cybermomo.daydreamer.world \
  --backend-url http://127.0.0.1:13011
```

该命令检查内部 backend health、正式前端 HTML、同域 `/api/auth/me`，不调用模型或写入数据。脚本中的默认 URL 与 GitHub `Production smoke` workflow 仍是旧 Railway 路径，标为待迁移的运维工具；不要直接使用无参数命令，也不要把旧 workflow 结果当作现役健康凭证。本次知识收尾不修改应用和 CI 执行逻辑。

### 6.2 必须人工的验收

- 登录/OAuth：真实账号 callback、session、登出、新旧用户落地页。
- Agent Chat/Summary/核心 Prompt：授权测试账号 + 真实模型质量。
- Voice Audit、单轮/批量重跑、生产数据/admin 写操作：须有覆盖具体动作与目标的用户授权，范围未变不重复确认，并记录范围、恢复方案和结果。
- 中国移动网络：确有可用性要求时由真人使用 4G/5G 验证，并把结果写入 workflow input 或 PR。

## 7. Truth sync 与清理

验收通过后再同步 README、AGENTS.md、runbook ；Agent 记忆仅在用户明确要求且宿主允许时更新。记忆必须标明已验证的 commit/部署事实，不得包含 secret 或用户数据。

用户确认任务完成后，再删除远程/本地分支、worktree 和临时资源；高风险任务保留必要的验收和回滚记录。

## 8. 分阶段完成定义

- Phase 1：任务边界、风险分级、独立分支/worktree、PR template 和基础 CI 已落地。
- Phase 2：`main` 分支保护已启用，任务边界/风险 CI gate、required checks、review、按用户授权执行 merge 成为交付路径。
- Phase 3：部署后只读 smoke、Railway 证据记录、真实账号/模型/生产数据人工门禁、truth-sync 和确认后清理形成闭环。
