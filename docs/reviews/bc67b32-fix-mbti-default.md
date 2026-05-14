# Review · bc67b32 fix(mbti): 默认不勾「不知道 / 不想填」

**Reviewer**: CodeX
**Date**: 2026-05-14
**Verdict**: 通过

## 1. 变更摘要

这个 commit 修正 MBTI 选择器的初始状态:不再从 `value=null` 推断用户选择了“不知道 / 不想填”,避免新用户进入页面时四个维度被默认置灰。同步逻辑也只在外部传入完整 MBTI 时覆盖内部状态。

## 2. 必修项(blocker)

- 无

## 3. 建议项(可选优化)

- [ ] `apps/web/components/MbtiPicker.tsx:56`: 组件 mount 后会立即 `onChange(null)`,即使父级本来就是 null。当前父级 setState 同值通常不会造成可见问题,但后续如果父级把 onChange 接到表单 dirty 状态,可能会误标“已修改”。建议未来用 `useRef` 跳过首轮同步或只在值真实变化时回调。
- [ ] `apps/web/components/MbtiPicker.tsx:42`: 现在 `value=null` 不会清空四个维度,适合用户编辑中的半选状态;但如果外部 reset 真的想清空内部维度,当前组件做不到。建议如果未来有“重置表单”按钮,另加 explicit reset key。

## 4. 安全性 / 边界 case 检查

- [x] 输入校验是否完备(SQL 注入 / XSS / SSRF / 数据 size): 前端状态变更,不涉及直接安全输入;最终后端 `mbti` 仍有长度上限但没有枚举校验,可在 Task A profile 测试中补边界。
- [x] auth / authz 是否正确: 不涉及。
- [x] DB 事务边界是否合理: 不涉及。
- [x] error path 是否会泄漏内部信息: 不涉及。

## 5. 性能检查

- [x] N+1 query: 不涉及。
- [x] 不必要的 await / round-trip: 不涉及。
- [x] 长任务有没有阻塞 event loop: 不涉及。
- [x] DB 连接池占用: 不涉及。

## 6. 与 AGENTS.md §3 铁律的兼容性

- [x] §3.1 平台底线 vs Agent 拉黑数据隔离: 不涉及。
- [x] §3.2 Agent 行为约束在平台 prompt: 不涉及。
- [x] §3.3 朋友式八卦语气: 不涉及,这是资料表单控件。
- [x] §3.4 .md 不向他人暴露: 不涉及。
- [x] §3.5 prompt 改动权限: 不涉及。

## 7. 测试覆盖建议(为 Task A 准备的)

- 首次渲染 `value=null` 时 unknown checkbox 不应默认勾选。
- 用户主动勾 unknown 后,父级收到 `onChange(null)`,checkbox 保持勾选且维度区置灰。
- 用户选择完整 `INFJ` 后,父级收到 `onChange("INFJ")`。
- 用户先选完整 MBTI,再取消其中一维后,父级收到 `onChange(null)`,unknown 仍为 false。
- 外部把 value 从 null 改成完整 MBTI 时,四维状态同步并清掉 unknown。
- 确认 effect 不会在 value=null 与 unknown 状态之间形成循环。
