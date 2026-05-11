"use client"

/**
 * /me/agent · 跟自己 Agent 的所有对话列表
 *
 * 每个会话点开 → /me/agent/{id} 看完整消息流。
 * 4 种 scope:
 *  - general : 用户主动开的全局对话
 *  - room    : 简报「跟我 Agent 聊聊」起头的
 *  - revisit : 真人聊天结束后 Agent 主动回访
 *  - plaza   : (Phase 3 上线后)广场点击像素点起头
 */
import Link from "next/link"
import { useEffect, useState } from "react"

import Topbar from "@/components/Topbar"
import { api, type AgentConversation } from "@/lib/api"

const SCOPE_LABEL: Record<string, { label: string; className: string }> = {
  general: { label: "随便聊", className: "bg-bg-soft text-ink-secondary" },
  room:    { label: "简报后调方向", className: "bg-primary-soft text-primary-dark" },
  revisit: { label: "Agent 回访", className: "bg-[rgba(255,215,0,0.18)] text-[#9a7800]" },
  plaza:   { label: "广场探问", className: "bg-bg-soft text-ink-secondary" },
}

export default function MyAgentConversationsPage() {
  const [items, setItems] = useState<AgentConversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { void load() }, [])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<AgentConversation[]>("/api/me/agent/conversations")
      setItems(data || [])
    } catch (e: any) {
      setError(e?.detail || e?.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  async function startNew() {
    try {
      const conv = await api.post<AgentConversation>(
        "/api/me/agent/conversations",
        { scope: "general" },
      )
      // 跳到新会话
      window.location.href = `/me/agent/${conv.id}`
    } catch (e: any) {
      setError(e?.detail || e?.message || "新建会话失败")
    }
  }

  return (
    <div className="min-h-screen">
      <Topbar active="me" />

      <main className="max-w-[640px] mx-auto px-6 py-8 pb-24">
        <header className="mb-6">
          <Link href="/me" className="text-xs text-ink-secondary hover:text-ink mb-3 inline-flex items-center gap-1">
            ← 返回我的
          </Link>
          <div className="flex items-center justify-between mt-2 gap-3">
            <div>
              <h1 className="text-xl font-semibold">跟我的 Agent</h1>
              <p className="text-sm text-ink-tertiary mt-1.5 leading-relaxed">
                所有跟你 Agent 的对话都在这。你随时可以开一个新的。
              </p>
            </div>
            <button
              onClick={startNew}
              className="bg-primary text-white px-4 py-2 rounded-full font-medium text-sm hover:bg-primary-dark transition whitespace-nowrap"
            >
              + 新对话
            </button>
          </div>
        </header>

        {loading && <p className="text-center py-12 text-ink-secondary">加载中…</p>}

        {error && (
          <div className="bg-warn-soft text-warn rounded-md px-4 py-3 text-sm mb-6">
            {error} <button onClick={load} className="underline ml-2">再试</button>
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="bg-bg-elevated border border-dashed border-line rounded-lg px-8 py-16 text-center">
            <h3 className="text-base font-semibold mb-2">还没跟 Agent 聊过</h3>
            <p className="text-sm text-ink-secondary leading-relaxed mb-6">
              你可以从简报上点「跟我 Agent 聊聊」开始,或者用右下浮动按钮直接开口。
            </p>
            <button
              onClick={startNew}
              className="bg-primary text-white px-5 py-2 rounded-full font-medium text-sm hover:bg-primary-dark transition"
            >
              直接开一个 →
            </button>
          </div>
        )}

        <div className="space-y-2.5">
          {items.map(c => {
            const scope = SCOPE_LABEL[c.scope] || SCOPE_LABEL.general
            const when = c.last_message_at || c.created_at
            return (
              <Link
                key={c.id}
                href={`/me/agent/${c.id}`}
                className="block bg-bg-elevated border border-line-soft hover:border-line rounded-md px-4 py-3 transition"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <span className={`text-[10px] rounded-full px-2 py-0.5 ${scope.className}`}>
                        {scope.label}
                      </span>
                      {c.title && (
                        <span className="text-sm font-medium truncate">{c.title}</span>
                      )}
                    </div>
                    {c.last_message_preview && (
                      <p className="text-sm text-ink-secondary leading-relaxed line-clamp-2">
                        {c.last_message_preview}
                      </p>
                    )}
                    <div className="text-xs text-ink-tertiary mt-1.5">
                      {new Date(when).toLocaleString("zh-CN")}
                    </div>
                  </div>
                  <span className="text-xs text-primary-dark font-medium flex-shrink-0">进入 →</span>
                </div>
              </Link>
            )
          })}
        </div>
      </main>
    </div>
  )
}
