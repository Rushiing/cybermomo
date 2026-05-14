# Review · 2c73f6a feat(avatar): 头像上传启用

**Reviewer**: CodeX
**Date**: 2026-05-14
**Verdict**: 有问题需修

## 1. 变更摘要

这个 commit 打通头像上传 MVP 路径:前端新增 `AvatarUpload`,把本地图片压成 256x256 JPEG data URL 后随 profile 保存;后端放宽 `avatar_url` 长度并允许 http(s) 或 `data:image/...;base64,...`;同时在 `UserMeResponse` 暴露 `google_avatar_url`。

## 2. 必修项(blocker)

- [ ] `apps/api/src/auth/schemas.py:33`: `avatar_url` 只检查 `data:image/` 前缀,会接受 `data:image/svg+xml;base64,...`。SVG 虽然放进 `<img>` 时多数浏览器禁脚本,但它仍是可脚本/外链能力复杂的 XML 图片格式,不适合作为用户可控 data URL 直存直显。建议后端白名单限制为 `image/jpeg` / `image/png` / `image/webp` / `image/gif`,或 MVP 直接只收 `data:image/jpeg;base64,` 与 http(s) Google 头像。

## 3. 建议项(可选优化)

- [ ] `apps/api/src/auth/schemas.py:31`: http(s) URL 当前不限制来源。若只支持 Google 头像复用,建议后续限制为已知 Google avatar host,否则任意外链头像会带来隐私追踪、混合内容和内容稳定性问题。
- [ ] `apps/api/src/auth/schemas.py:35`: data URL 只检查 payload 非空,没有校验 base64 是否可解码。建议 `base64.b64decode(payload, validate=True)` 并按解码后字节数检查上限。
- [ ] `apps/web/components/AvatarUpload.tsx:56`: 前端用 `dataUrl.length` 近似 200KB,与后端 `max_length` 一致但不是真正字节数;如果后端改成解码后字节上限,这里也要同步。
- [ ] `apps/web/components/AvatarUpload.tsx:48`: `file.type.startsWith("image/")` 会接受 SVG。即使后端修了,前端也建议同步拒绝 `image/svg+xml`,减少用户困惑。
- [ ] `apps/web/components/AvatarUpload.tsx:173`: 所有图片都强制放大到 256x256。原图小于 256 的头像会被放大变糊;可选优化是小图只裁剪/补底或维持较小尺寸。
- [ ] CSP: 当前 feature 依赖 `<img src="data:...">`,部署侧如果之后收紧 `img-src`,需要显式允许 `data:` 和 Google 头像域名。

## 4. 安全性 / 边界 case 检查

- [ ] 输入校验是否完备(SQL 注入 / XSS / SSRF / 数据 size): SQL 注入不涉及;size 有字符串上限;data URL MIME/base64 校验不够,SVG 必须处理。
- [x] auth / authz 是否正确: profile 写入仍走 `CurrentUser`,只能改自己的 profile。
- [x] DB 事务边界是否合理: 没有新增事务边界问题。
- [x] error path 是否会泄漏内部信息: Pydantic 422 会暴露字段校验原因,可接受。

## 5. 性能检查

- [x] N+1 query: 不涉及新增列表查询。
- [x] 不必要的 await / round-trip: 前端本地压缩后一次 PUT;后端无额外 round-trip。
- [ ] 长任务有没有阻塞 event loop: 后端不处理图片;前端 canvas 压缩在主线程,大图可能短暂卡顿,但 MVP 可接受。
- [x] DB 连接池占用: 头像以 Text 存 DB,不会额外占用连接;但 200KB/profile 会增加行体积和备份体积,需要后续迁移 storage 时规划。

## 6. 与 AGENTS.md §3 铁律的兼容性

- [x] §3.1 平台底线 vs Agent 拉黑数据隔离: 不涉及。
- [x] §3.2 Agent 行为约束在平台 prompt: 不涉及。
- [x] §3.3 朋友式八卦语气: 不涉及,这是资料编辑 UI。
- [x] §3.4 .md 不向他人暴露: 合规。只新增头像字段,没有暴露 `.md` 原文。
- [x] §3.5 prompt 改动权限: 不涉及。

## 7. 测试覆盖建议(为 Task A 准备的)

- `PUT /me/profile` 接受 `https://...` avatar_url。
- `PUT /me/profile` 接受 `data:image/jpeg;base64,...` avatar_url。
- `PUT /me/profile` 拒绝 `data:text/html,...`。
- `PUT /me/profile` 拒绝 `javascript:alert(1)`。
- `PUT /me/profile` 空字符串 avatar_url 转成 None。
- `PUT /me/profile` 超过 200KB 返回 422。
- 补一条 `data:image/svg+xml;base64,...` 应返回 422,用于锁住本次 review 的安全修复。
- `GET /me` / register / login 的 `UserMeResponse` 都包含 `google_avatar_url` 字段。
