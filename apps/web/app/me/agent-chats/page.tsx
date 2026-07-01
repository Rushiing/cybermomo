"use client"

/**
 * /me/agent-chats · "Agent 替我聊过谁" 历史档案
 *
 * - 列出 GET /api/agent_chat/me 的所有场次,started_at desc
 * - re_dispatched(被换话题再派的旧场)默认折叠 — 用户主动选择否决,但记录有诊断价值
 * - 点击 → 打开 AgentChatViewer modal(铁律:对方 private_signals 永不暴露)
 * - 支持 ?focus=summary_id 自动打开那张
 */
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useMemo, useState } from "react"

import AgentChatViewer from "@/components/AgentChatViewer"
import Topbar from "@/components/Topbar"
import { api } from "@/lib/api"

interface AgentChatHistoryItem {
  agent_chat_id: number
  match_id: number
  peer_user_id: number
  peer_nickname?: string | null
  status: string
  end_reason?: string | null
  turns: number
  started_at?: string | null
  related_summary_id?: number | null
  related_verdict?: string | null
  user_decision?: string | null
}

// Next.js App Router 要求 useSearchParams() 包在 Suspense 里,
// 否则 build 时静态预渲染失败(missing-suspense-with-csr-bailout)
export default function Page() {
  return (
    <Suspense fallback={<PageFallback />}>
      <MyAgentChatsPage />
    </Suspense>
  )
}

function PageFallback() {
  return (
    <div className="min-h-screen">
      <Topbar active="me" />
      <main className="max-w-[640px] mx-auto px-6 py-8 pb-24">
        <p className="text-center py-12 text-ink-secondary">加载中…</p>
      </main>
    </div>
  )
}

function MyAgentChatsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const focusId = searchParams.get("focus")

  const [items, setItems] = useState<AgentChatHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showRedispatched, setShowRedispatched] = useState(false)
  const [viewerSummaryId, setViewerSummaryId] = useState<number | null>(null)

  useEffect(() => {
    void load()
  }, [])

  // 处理 ?focus=N
  useEffect(() => {
    if (focusId && !loading && items.length > 0) {
      const fid = Number(focusId)
      if (!Number.isNaN(fid)) setViewerSummaryId(fid)
    }
  }, [focusId, loading, items.length])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<AgentChatHistoryItem[]>("/api/agent_chat/me")
      setItems(data || [])
    } catch (e: any) {
      setError(e?.detail || e?.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  const { active, redispatched } = useMemo(() => {
    const active: AgentChatHistoryItem[] = []
    const redispatched: AgentChatHistoryItem[] = []
    items.forEach(c => {
      if (c.status === "re_dispatched") redispatched.push(c)
      else active.push(c)
    })
    return { active, redispatched }
  }, [items])

  function closeViewer() {
    setViewerSummaryId(null)
    // 把 ?focus=... 从 URL 摘掉,避免再次打开就直接弹出
    if (focusId) router.replace("/me/agent-chats")
  }

  return (
    <div className="min-h-screen">
      <Topbar active="me" />

      <main className="max-w-[640px] mx-auto px-6 py-8 pb-24">
        <header className="mb-6">
          <Link href="/me" className="text-xs text-ink-secondary hover:text-ink mb-3 inline-flex items-center gap-1">
            ← 返回我的
          </Link>
          <h1 className="text-xl font-semibold mt-2">Agent 替我聊过谁</h1>
          <p className="text-sm text-ink-tertiary mt-1.5 leading-relaxed">
            我替你聊过的所有人都在这。点开看那场聊了什么 — 选择权在你。
            <br />
            <span className="text-[12px]">对方 Agent 的私下判断不会展示。</span>
          </p>
        </header>

        {loading && <p className="text-center py-12 text-ink-secondary">加载中…</p>}

        {error && (
          <div className="bg-warn-soft text-warn rounded-md px-4 py-3 text-sm mb-6">
            {error} <button onClick={load} className="underline ml-2">再试</button>
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="bg-bg-elevated border border-dashed border-line rounded-lg px-8 py-16 text-center">
            <h3 className="text-base font-semibold mb-2">还没有 Agent 互聊记录</h3>
            <p className="text-sm text-ink-secondary leading-relaxed">
              生成 .md 之后,Agent 会去认识平台上的其他人 — 那些会出现在这里。
            </p>
          </div>
        )}

        {/* === 主列表 === */}
        {active.length > 0 && (
          <div className="space-y-2.5">
            {active.map(c => (
              <ChatRow key={c.agent_chat_id} c={c} onOpen={(id) => setViewerSummaryId(id)} />
            ))}
          </div>
        )}

        {/* === 已被换话题再派(折叠)=== */}
        {redispatched.length > 0 && (
          <section className="mt-8">
            <button
              onClick={() => setShowRedispatched(v => !v)}
              className="text-xs text-ink-secondary hover:text-ink flex items-center gap-2 mb-3"
            >
              <span>{showRedispatched ? "▼" : "▶"}</span>
              <span>已被换话题再派的 {redispatched.length} 场</span>
              <span className="text-ink-tertiary">— 你当时选了「再派一次」,这些是旧场</span>
            </button>
            {showRedispatched && (
              <div className="space-y-2.5">
                {redispatched.map(c => (
                  <ChatRow key={c.agent_chat_id} c={c} onOpen={(id) => setViewerSummaryId(id)} muted />
                ))}
              </div>
            )}
          </section>
        )}
      </main>

      {viewerSummaryId && (
        <AgentChatViewer
          summaryId={viewerSummaryId}
          open={true}
          onClose={closeViewer}
        />
      )}
    </div>
  )
}

function ChatRow({
  c,
  onOpen,
  muted,
}: {
  c: AgentChatHistoryItem
  onOpen: (summaryId: number) => void
  muted?: boolean
}) {
  const canOpen = c.related_summary_id != null
  const verdictBadge = c.related_verdict ? (
    <span className={`text-xs px-2 py-0.5 rounded-full ${verdictBadgeClass(c.related_verdict)}`}>
      {c.related_verdict}
    </span>
  ) : null

  const displayName = c.peer_nickname || "这位用户"
  const avatarChar = (c.peer_nickname || "对").charAt(0)

  const Inner = (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">
          {avatarChar}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm flex-wrap">
            <span className="font-medium">{c.peer_nickname ? `@${displayName}` : displayName}</span>
            {verdictBadge}
            {c.status === "running" && (
              <span className="text-[10px] text-primary-dark border border-primary-soft rounded-full px-1.5 py-0.5">聊着</span>
            )}
            {c.status === "done_terminated" && (
              <span className="text-[10px] text-warn border border-warn-soft rounded-full px-1.5 py-0.5">中断</span>
            )}
          </div>
          <div className="text-xs text-ink-tertiary mt-1">
            {c.turns} 轮
            {c.started_at && <> · {new Date(c.started_at).toLocaleString("zh-CN")}</>}
            {c.user_decision && <> · 已决策:{decisionLabel(c.user_decision)}</>}
          </div>
        </div>
      </div>
      {canOpen ? (
        <span className="text-xs text-primary-dark font-medium flex-shrink-0">看回放 →</span>
      ) : (
        <span className="text-xs text-ink-tertiary flex-shrink-0">无关联简报</span>
      )}
    </div>
  )

  if (!canOpen) {
    return (
      <div className={`bg-bg-elevated border border-line-soft rounded-md px-4 py-3 ${muted ? "opacity-70" : ""}`}>
        {Inner}
      </div>
    )
  }

  return (
    <button
      onClick={() => onOpen(c.related_summary_id!)}
      className={`w-full text-left bg-bg-elevated border border-line-soft hover:border-line rounded-md px-4 py-3 transition cursor-pointer ${
        muted ? "opacity-70 hover:opacity-100" : ""
      }`}
    >
      {Inner}
    </button>
  )
}

function verdictBadgeClass(v: string): string {
  if (v === "来电") return "bg-primary-soft text-primary-dark"
  if (v === "不合") return "bg-bg border border-line-soft text-ink-tertiary"
  return "bg-[rgba(255,215,0,0.15)] text-[#9a7800]"
}

function decisionLabel(d: string): string {
  const map: Record<string, string> = {
    open_human_chat: "开聊",
    re_dispatch: "再派",
    drop: "丢",
    chat_with_my_agent: "调方向",
  }
  return map[d] || d
}
