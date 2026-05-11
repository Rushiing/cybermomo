"use client"

/**
 * /me/agent/[id] · 单个 Agent 对话视图(全屏)
 *
 * 跟 AgentFloatingWidget 的抽屉版共用 AgentConversationView,布局不同:
 * - 整页全屏(浮窗是右侧抽屉)
 * - 有 Topbar + 返回链接
 */
import Link from "next/link"
import { useEffect, useState } from "react"

import AgentConversationView from "@/components/AgentConversationView"
import Topbar from "@/components/Topbar"
import { api, type AgentConversation } from "@/lib/api"

const SCOPE_LABEL: Record<string, string> = {
  general: "随便聊",
  room:    "简报后调方向",
  revisit: "Agent 回访",
  plaza:   "广场探问",
}

export default function AgentConversationPage({
  params,
}: {
  params: { id: string }
}) {
  const conversationId = Number(params.id)

  const [conv, setConv] = useState<AgentConversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void loadMeta()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  async function loadMeta() {
    setLoading(true)
    setError(null)
    try {
      const c = await api.get<AgentConversation>(
        `/api/me/agent/conversations/${conversationId}`,
      )
      setConv(c)
    } catch (e: any) {
      setError(e?.detail || e?.message || "会话不存在或不属于你")
    } finally {
      setLoading(false)
    }
  }

  if (Number.isNaN(conversationId)) {
    return (
      <div className="min-h-screen">
        <Topbar active="me" />
        <main className="max-w-[640px] mx-auto px-6 py-8">
          <p className="text-warn">无效会话 id</p>
        </main>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col">
      <Topbar active="me" />

      <div className="max-w-[720px] mx-auto w-full px-6 pt-4 flex-shrink-0">
        <Link href="/me/agent" className="text-xs text-ink-secondary hover:text-ink inline-flex items-center gap-1">
          ← 全部会话
        </Link>
        {conv && (
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <h1 className="font-semibold text-base">
              {conv.title || "跟你的 Agent"}
            </h1>
            <span className="text-[10px] text-ink-secondary border border-line-soft rounded-full px-2 py-0.5">
              {SCOPE_LABEL[conv.scope] || conv.scope}
            </span>
          </div>
        )}
      </div>

      <div className="flex-1 max-w-[720px] mx-auto w-full overflow-hidden mt-3">
        {loading && (
          <p className="text-center text-ink-secondary text-sm py-12">加载中…</p>
        )}
        {error && (
          <div className="mx-6 my-6 bg-warn-soft text-warn rounded-md px-4 py-3 text-sm">
            {error}
          </div>
        )}
        {!loading && !error && conv && (
          <AgentConversationView conversationId={conversationId} />
        )}
      </div>
    </div>
  )
}
