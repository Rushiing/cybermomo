## 任务边界

- 要解决：
- 不改：
- 验收标准：

## 风险等级

- [ ] 低：文档、测试、不改行为的文案或只读工具
- [ ] 中：普通 UI/API、性能、依赖或部署配置
- [ ] 高：OAuth/登录、生产数据、migration、Agent/Summary 核心 Prompt、Voice Audit 写入、单轮/批量重跑、admin 权限

高风险任务：

- [ ] 用户已确认任务边界
- [ ] 部署或生产操作前需再次人工确认
- [ ] 已写明回滚/恢复方案

## 变更与验证

- 变更摘要：
- 本地验证命令与结果：
- 未验证项：

## 部署与线上验收

- 影响服务：[ ] 无 [ ] backend [ ] frontend [ ] cron [ ] Postgres
- 是否包含 migration：[ ] 否 [ ] 是
- [ ] Railway 运行 commit 与 merge commit 一致
- [ ] backend `/healthz` 正常
- [ ] frontend 正式域名可达且页面正常
- [ ] frontend 同域 `/api` 可连接 backend
- [ ] 已验收本 PR 影响的真实用户路径
- [ ] 需要时已完成真实移动网络验收

## Truth sync 与清理

- [ ] 需要时已同步 README / AGENTS.md / runbook
- [ ] 用户确认完成后再删除分支、worktree 和临时资源

