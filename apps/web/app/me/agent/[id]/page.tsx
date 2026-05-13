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
  revisit: "聊后回访",
  plaza:   "广场探问",
}

/** 从 context_refs 拼一个易读的"对话锚定主体"显示 */
function getConversationAnchor(conv: AgentConversation): {
  peerName?: string
  state?: string  // verdict / exit_action 转中文
} {
  const refs = conv.context_refs || {}
  const peerName: string | undefined = refs.peer_nickname
    || (refs.peer_user_id ? `user_${refs.peer_user_id}` : undefined)

  let state: string | undefined
  if (conv.scope === "room") {
    state = refs.verdict ? `${refs.verdict}` : undefined
  } else if (conv.scope === "revisit") {
    const action = refs.exit_action
    state = {
      quit: "聊完",
      silent: "聊着没下文",
      block: "已拉黑",
      report: "已举报",
    }[action as string] || "聊后回访"
  } else if (conv.scope === "plaza") {
    state = "广场探问"
  }
  return { peerName, state }
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
        {conv && (() => {
          const { peerName, state } = getConversationAnchor(conv)
          const avatarChar = (peerName || "?").charAt(0)
          return (
            <div className="mt-3 flex items-center gap-3">
              {peerName && (
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary text-white text-sm font-semibold flex items-center justify-center flex-shrink-0">
                  {avatarChar}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="font-semibold text-[17px] truncate">
                    {peerName ? `跟我聊 @${peerName}` : (conv.title || "跟你的 Agent")}
                  </h1>
                  {state && (
                    <span className={`text-[11px] rounded-full px-2 py-0.5 ${
                      state === "来电" ? "bg-primary-soft text-primary-dark"
                      : state === "不合" ? "bg-bg-soft text-ink-tertiary"
                      : state === "已拉黑" || state === "已举报" ? "bg-warn-soft text-warn"
                      : "bg-[rgba(255,215,0,0.18)] text-[#9a7800]"
                    }`}>
                      {state}
                    </span>
                  )}
                  <span className="text-[10px] text-ink-tertiary border border-line-soft rounded-full px-1.5 py-0.5">
                    {SCOPE_LABEL[conv.scope] || conv.scope}
                  </span>
                </div>
                <p className="text-[12px] text-ink-tertiary mt-0.5">
                  这场对话是关于 {peerName ? `@${peerName}` : "对方"} 的。
                </p>
              </div>
            </div>
          )
        })()}
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
