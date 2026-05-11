"""
08 · 跟自己 Agent 对话(§4.10)

宿主跟自己 Agent 的全局对话系统。
- 入口:右下浮动 Agent、简报上点「跟我 Agent 聊聊」、真人聊天后 Agent 回访等
- RAG:基于宿主 .md + 历史 summary + 上次对话片段(pgvector / text-embedding-v3)
- 铁律:
  · .md 字面原文不暴露(连给宿主自己也只暴露切片摘要,不直接 dump JSON)
  · 对方 Agent 的 private_signals 不进入本 Agent 的 prompt 上下文
"""
