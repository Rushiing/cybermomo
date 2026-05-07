"use client"

/**
 * 屏 17-18 · 真人聊天室 + callout 抽屉
 *
 * GET /api/chat/sessions/{id}/messages(轮询 3s 拿新消息,SSE 留作后期)
 * POST /api/chat/sessions/{id}/messages
 * POST /api/chat/sessions/{id}/callout
 * POST /api/chat/sessions/{id}/exit
 */
import { useRouter } from "next/navigation"
import { useEffect, useRef, useState } from "react"

import {
  api,
  type CalloutResponse,
  type ChatMessageResponse,
  type ChatSessionResponse,
  getMockUserId,
} from "@/lib/api"

export default function ChatRoomPage({ params }: { params: { sessionId: string } }) {
  const router = useRouter()
  const sessionId = Number(params.sessionId)
  const myUid = Number(getMockUserId())

  const [session, setSession] = useState<ChatSessionResponse | null>(null)
  const [messages, setMessages] = useState<ChatMessageResponse[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [callouts, setCallouts] = useState<CalloutResponse[]>([])
  const [calloutDraft, setCalloutDraft] = useState("")
  const [calloutPending, setCalloutPending] = useState(false)

  const [menuOpen, setMenuOpen] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => { void loadInitial() }, [sessionId])
  useEffect(() => {
    const t = setInterval(() => { void pollMessages() }, 3000)
    return () => clearInterval(t)
  }, [sessionId])

  async function loadInitial() {
    try {
      const [s, msgs, cs] = await Promise.all([
        api.get<ChatSessionResponse>(`/api/chat/sessions/${sessionId}`),
        api.get<ChatMessageResponse[]>(`/api/chat/sessions/${sessionId}/messages`),
        api.get<CalloutResponse[]>(`/api/chat/sessions/${sessionId}/callouts`),
      ])
      setSession(s)
      setMessages(msgs)
      setCallouts(cs)
      scrollToBottom()
    } catch (e: any) {
      alert(`加载失败:${e?.detail || e?.message}`)
    }
  }

  async function pollMessages() {
    try {
      const msgs = await api.get<ChatMessageResponse[]>(`/api/chat/sessions/${sessionId}/messages`)
      if (msgs.length !== messages.length) {
        setMessages(msgs)
        scrollToBottom()
      }
    } catch { /* swallow */ }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    })
  }

  async function send() {
    if (!draft.trim() || sending) return
    setSending(true)
    try {
      const msg = await api.post<ChatMessageResponse>(`/api/chat/sessions/${sessionId}/messages`, {
        content_type: "text",
        content: draft.trim(),
      })
      setMessages([...messages, msg])
      setDraft("")
      scrollToBottom()
    } catch (e: any) {
      alert(`发送失败:${e?.detail || e?.message}`)
    } finally {
      setSending(false)
    }
  }

  async function callout() {
    if (!calloutDraft.trim() || calloutPending) return
    setCalloutPending(true)
    try {
      const c = await api.post<CalloutResponse>(`/api/chat/sessions/${sessionId}/callout`, {
        callout_prompt: calloutDraft.trim(),
      })
      setCallouts([...callouts, c])
      setCalloutDraft("")
    } catch (e: any) {
      alert(`callout 失败:${e?.detail || e?.message}`)
    } finally {
      setCalloutPending(false)
    }
  }

  async function exit(action: "quit" | "block" | "report") {
    const confirmed = action === "quit" || confirm(action === "block" ? "确认拉黑对方?" : "确认举报?")
    if (!confirmed) return
    try {
      await api.post(`/api/chat/sessions/${sessionId}/exit`, { action })
      router.push("/room")
    } catch (e: any) {
      alert(`退出失败:${e?.detail || e?.message}`)
    }
  }

  const otherUid = session ? (session.user_a_id === myUid ? session.user_b_id : session.user_a_id) : null
  const sessionEnded = session?.status !== "active"

  return (
    <div className="h-screen flex flex-col bg-bg">
      {/* 顶部 */}
      <header className="bg-bg border-b border-line-soft px-6 flex items-center gap-4 h-[60px] flex-shrink-0 relative">
        <button onClick={() => router.push("/room")} className="w-9 h-9 rounded-md hover:bg-bg-soft flex items-center justify-center">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="flex items-center gap-3 flex-1">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary text-white text-sm font-semibold flex items-center justify-center flex-shrink-0">
            {otherUid ? `U${otherUid}` : "?"}
          </div>
          <div>
            <div className="font-semibold text-[15px]">@user_{otherUid}</div>
            <div className="text-[11.5px] text-ink-secondary flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-primary" />
              {sessionEnded ? `已结束(${session?.status})` : "在线"}
            </div>
          </div>
        </div>
        <button onClick={() => setMenuOpen(!menuOpen)} className="w-9 h-9 rounded-md hover:bg-bg-soft flex items-center justify-center">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/>
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute top-14 right-4 bg-bg-elevated border border-line-soft rounded-md shadow-modal py-2 min-w-[180px] z-30">
            <MenuItem onClick={() => router.push(`/chat/${sessionId}/briefing`)}>重读 Agent 简报</MenuItem>
            <MenuItem onClick={() => exit("quit")}>退出聊天</MenuItem>
            <hr className="border-line-soft my-1.5" />
            <MenuItem warn onClick={() => exit("block")}>拉黑 TA</MenuItem>
            <MenuItem warn onClick={() => exit("report")}>举报</MenuItem>
          </div>
        )}
      </header>

      {/* 消息流 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto bg-bg">
        <div className="max-w-[760px] mx-auto px-6 py-6 flex flex-col gap-1.5">
          {messages.length === 0 && (
            <div className="text-center text-xs text-ink-tertiary my-8">
              你们现在可以聊了。Agent 不在场,但你随时可以叫 ta 出来帮忙。
            </div>
          )}
          {messages.map(m => {
            const isMe = m.sender_user_id === myUid
            return (
              <div key={m.id} className={`flex ${isMe ? "justify-end" : "justify-start"} mt-0.5`}>
                <div className={`max-w-[70%] px-3.5 py-2.5 rounded-2xl text-[14.5px] leading-relaxed ${
                  isMe ? "bg-primary text-white rounded-br-sm" : "bg-bg-elevated border border-line-soft rounded-bl-sm"
                }`}>
                  {m.content}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 输入栏 */}
      {!sessionEnded && (
        <div className="border-t border-line-soft bg-bg px-6 py-3 flex-shrink-0">
          <div className="max-w-[760px] mx-auto flex items-center gap-2 bg-bg-elevated border border-line-soft rounded-xl pl-3 pr-1.5 py-1.5">
            <input
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send() } }}
              placeholder="发条消息"
              className="flex-1 bg-transparent border-0 outline-none px-1 py-2 text-[14.5px]"
            />
            <button
              onClick={() => setDrawerOpen(true)}
              className="w-9 h-9 rounded-full border-[1.5px] border-primary flex items-center justify-center hover:bg-primary-soft transition"
              title="问问你的 Agent · TA 不会看见"
            >
              <span className="block w-2 h-2 rounded-full bg-primary" />
            </button>
            <button
              onClick={() => void send()}
              disabled={!draft.trim() || sending}
              className="bg-primary text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed"
            >
              发送
            </button>
          </div>
        </div>
      )}

      {/* Callout drawer */}
      {drawerOpen && (
        <CalloutDrawer
          callouts={callouts}
          draft={calloutDraft}
          setDraft={setCalloutDraft}
          pending={calloutPending}
          onSend={() => void callout()}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  )
}

function MenuItem(props: { children: React.ReactNode; onClick: () => void; warn?: boolean }) {
  return (
    <button
      onClick={() => { props.onClick() }}
      className={`block w-full text-left px-3 py-2 text-sm rounded-md transition ${
        props.warn ? "text-warn hover:bg-warn-soft" : "hover:bg-bg-soft"
      }`}
    >{props.children}</button>
  )
}

function CalloutDrawer(p: {
  callouts: CalloutResponse[]
  draft: string
  setDraft: (s: string) => void
  pending: boolean
  onSend: () => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={p.onClose} />
      <div className="absolute bottom-0 left-0 right-0 bg-bg rounded-t-xl shadow-drawer h-[62vh] flex flex-col animate-fade-in">
        <div className="w-9 h-1 bg-line rounded-full mx-auto mt-2" />
        <header className="flex items-center justify-between px-6 pt-4">
          <div className="flex items-center gap-2">
            <div className="relative">
              <span className="block w-2.5 h-2.5 rounded-full bg-primary" />
              <span className="absolute inset-[-3px] rounded-full border-[1.5px] border-primary opacity-40 animate-agent-pulse" />
            </div>
            <span className="font-semibold text-sm">你的 Agent</span>
          </div>
          <button onClick={p.onClose} className="w-8 h-8 rounded-md hover:bg-bg-soft flex items-center justify-center">×</button>
        </header>
        <div className="bg-primary-soft text-primary-dark text-xs px-3 py-2 mx-6 rounded-md mt-3 text-center">
          🔒 这是你和 Agent 的私人对话 · 对方不会看见
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4 flex flex-col gap-3">
          {p.callouts.length === 0 && (
            <div className="text-center text-xs text-ink-tertiary py-6">问问 Agent — 比如"她说的这事我不知道怎么接"</div>
          )}
          {p.callouts.flatMap(c => [
            <div key={`u-${c.id}`} className="self-end max-w-[88%] bg-bg-soft text-ink px-3.5 py-2.5 rounded-md rounded-br-sm text-sm leading-relaxed">
              {c.callout_prompt}
            </div>,
            <div key={`a-${c.id}`} className="self-start max-w-[88%] bg-bg-elevated border border-line-soft rounded-md rounded-tl-sm pl-7 pr-3.5 py-3 text-sm leading-relaxed relative">
              <span className="absolute left-3 top-3.5 w-2 h-2 rounded-full bg-primary" />
              {c.callout_response}
            </div>,
          ])}
        </div>
        <div className="border-t border-line-soft px-6 py-3 flex-shrink-0">
          <div className="flex gap-2 bg-bg-elevated border border-line-soft rounded-xl pl-3 pr-1.5 py-1.5 items-center">
            <input
              value={p.draft}
              onChange={e => p.setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); p.onSend() } }}
              placeholder="问问你的 Agent…"
              className="flex-1 bg-transparent outline-none px-1 py-2 text-sm"
            />
            <button
              onClick={p.onSend}
              disabled={!p.draft.trim() || p.pending}
              className="bg-primary text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed"
            >
              {p.pending ? "等…" : "发送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
