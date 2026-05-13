"use client"

/**
 * /me/agent/[id] · 单个 Agent 对话视图(全屏)
 *
 * 跟 AgentFloatingWidget 的抽屉版共用 AgentConversationView,布局不同:
 * - 整页全屏(浮窗是右侧抽屉)
 * - 有 Topbar + 返回链接
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import AgentConversationView from "@/components/AgentConversationView"
import Toast from "@/components/Toast"
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
  const router = useRouter()
  const conversationId = Number(params.id)

  const [conv, setConv] = useState<AgentConversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // 「用这个方向再派」modal
  const [redispatchOpen, setRedispatchOpen] = useState(false)
  const [direction, setDirection] = useState("")
  const [redispatching, setRedispatching] = useState(false)
  const [extracting, setExtracting] = useState(false)
  // Agent 明确给过方向(提炼到了)→ 标志位让 UI 显示"直接派"模式
  const [autoFilled, setAutoFilled] = useState(false)

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

  async function openRedispatch() {
    // 立刻开 modal,后台并行提炼方向
    setRedispatchOpen(true)
    setDirection("")
    setAutoFilled(false)
    setExtracting(true)
    try {
      const r = await api.post<{ suggested_direction: string | null }>(
        `/api/me/agent/conversations/${conversationId}/extract-direction`,
      )
      if (r.suggested_direction && r.suggested_direction.trim()) {
        setDirection(r.suggested_direction.trim())
        setAutoFilled(true)
      }
    } catch {
      /* 提炼失败也没关系 — fallback 到空 textarea */
    } finally {
      setExtracting(false)
    }
  }

  async function submitRedispatch() {
    if (!direction.trim()) return
    setRedispatching(true)
    try {
      await api.post(
        `/api/me/agent/conversations/${conversationId}/redispatch`,
        { direction_hint: direction.trim() },
      )
      setRedispatchOpen(false)
      setDirection("")
      setAutoFilled(false)
      setNotice("收到 — 我用这个方向去跟 TA 再聊一场,大概一分钟回房间给你新简报。")
      // 等 1.5s 跳回 /room,让用户看到新简报陆续到来
      setTimeout(() => router.push("/room"), 1500)
    } catch (e: any) {
      setNotice(`再派失败:${e?.detail || e?.message}`)
    } finally {
      setRedispatching(false)
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

  const canRedispatch = conv?.scope === "room"

  return (
    <div className="h-screen flex flex-col">
      <Topbar active="me" />
      <Toast message={notice} onClose={() => setNotice(null)} />

      <div className="max-w-[720px] mx-auto w-full px-6 pt-4 flex-shrink-0">
        <Link href="/me/agent" className="text-xs text-ink-secondary hover:text-ink inline-flex items-center gap-1">
          ← 全部会话
        </Link>
        {conv && (() => {
          const { peerName, state } = getConversationAnchor(conv)
          const avatarChar = (peerName || "?").charAt(0)
          return (
            <div className="mt-3 flex items-start gap-3">
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
              {/* 右上 CTA · scope=room 才有 · 跟标题在同一行,不再浮动 */}
              {canRedispatch && (
                <button
                  onClick={openRedispatch}
                  className="text-xs text-primary-dark border-[1.5px] border-primary hover:bg-primary-soft rounded-full px-3 py-1.5 transition flex items-center gap-1.5 flex-shrink-0 font-medium"
                >
                  <span>🔁</span>
                  <span>用这个方向再派</span>
                </button>
              )}
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

      {/* Modal:Agent 已提炼方向时直接确认;没提炼到才让用户手敲 */}
      {redispatchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
            onClick={() => !redispatching && setRedispatchOpen(false)}
          />
          <div className="relative bg-bg rounded-lg shadow-modal max-w-md w-full p-6">
            {extracting ? (
              <>
                <h3 className="text-base font-semibold mb-1.5">这次让我往哪儿探?</h3>
                <p className="text-xs text-ink-tertiary mb-4 leading-relaxed">
                  正在让 Agent 从刚才的对话里提炼方向…
                </p>
                <div className="bg-bg-soft rounded-md px-3 py-6 text-center text-sm text-ink-tertiary animate-pulse">
                  ⌛ 提炼中…
                </div>
              </>
            ) : autoFilled ? (
              <>
                <h3 className="text-base font-semibold mb-1.5">就这个方向去派 Agent?</h3>
                <p className="text-xs text-ink-tertiary mb-3 leading-relaxed">
                  我从你刚才跟 Agent 的对话里提炼出来:
                </p>
                <div className="bg-primary-soft border-l-[3px] border-primary rounded-md px-3.5 py-3 text-[14px] text-ink leading-relaxed whitespace-pre-wrap mb-2">
                  {direction}
                </div>
                <details className="mt-2">
                  <summary className="text-[11.5px] text-ink-tertiary hover:text-ink-secondary cursor-pointer">
                    需要改一下?展开编辑
                  </summary>
                  <textarea
                    value={direction}
                    onChange={e => setDirection(e.target.value)}
                    rows={5}
                    maxLength={500}
                    className="mt-2 w-full resize-none border-[1.5px] border-line-soft rounded-md px-3 py-2.5 text-sm focus:outline-none focus:border-primary bg-bg-elevated"
                  />
                  <div className="text-[11px] text-ink-tertiary text-right mt-1">
                    {direction.length} / 500
                  </div>
                </details>
              </>
            ) : (
              <>
                <h3 className="text-base font-semibold mb-1.5">这次让我往哪儿探?</h3>
                <p className="text-xs text-ink-tertiary mb-4 leading-relaxed">
                  你刚跟 Agent 的对话里还没提到明确方向 — 一两句话告诉我重点聊哪个方向,
                  我去跟 TA 的 Agent 再聊一场。
                </p>
                <textarea
                  value={direction}
                  onChange={e => setDirection(e.target.value)}
                  rows={4}
                  maxLength={500}
                  placeholder="比如:这次重点聊音乐演出 / 别再聊职场了 / 探探 TA 对长期关系的态度"
                  className="w-full resize-none border-[1.5px] border-line-soft rounded-md px-3 py-2.5 text-sm focus:outline-none focus:border-primary bg-bg-elevated"
                  autoFocus
                />
                <div className="text-[11px] text-ink-tertiary text-right mt-1">
                  {direction.length} / 500
                </div>
              </>
            )}
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                onClick={() => setRedispatchOpen(false)}
                disabled={redispatching}
                className="text-sm text-ink-secondary hover:text-ink px-3 py-2 transition"
              >
                取消
              </button>
              <button
                onClick={submitRedispatch}
                disabled={!direction.trim() || redispatching || extracting}
                className="bg-primary text-white px-5 py-2 rounded-full text-sm font-medium hover:bg-primary-dark transition disabled:opacity-40"
              >
                {redispatching ? "派出去中…" : autoFilled ? "就这个,派 →" : "派 Agent 去聊"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
