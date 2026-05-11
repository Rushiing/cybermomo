"use client"

/**
 * 跟自己 Agent 对话 · 消息流 + 输入框 + SSE 流式 token 渲染
 *
 * 用法:
 *   <AgentConversationView conversationId={N} />
 *
 * 行为:
 *  - 挂载时拉历史 messages
 *  - 用户提交输入 → 立刻显示用户气泡(乐观)+ 调 streamSSE
 *  - assistant token 增量渲染到一个临时气泡里
 *  - stream done 后 done event 不强制刷新(因为 user/assistant 后端已经落库,下次进来会拉到)
 *
 * 铁律提示:对话只展示给宿主本人 — 路由层已经 host scope 校验,这里假设可信。
 */
import { useEffect, useRef, useState } from "react"

import {
  api,
  type AgentConversationMessage,
  streamSSE,
} from "@/lib/api"

interface Props {
  conversationId: number
  /** 父容器是否需要在 viewport 内自动滚到底(默认 true) */
  autoScroll?: boolean
}

export default function AgentConversationView({
  conversationId,
  autoScroll = true,
}: Props) {
  const [messages, setMessages] = useState<AgentConversationMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [streamingText, setStreamingText] = useState("")
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    void loadMessages()
    // 切会话时取消上一次 stream
    return () => {
      abortRef.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
    }
  }, [messages.length, streamingText, autoScroll])

  async function loadMessages() {
    setLoading(true)
    setError(null)
    try {
      const list = await api.get<AgentConversationMessage[]>(
        `/api/me/agent/conversations/${conversationId}/messages`,
      )
      setMessages(list)
    } catch (e: any) {
      setError(e?.detail || e?.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  async function send() {
    const content = input.trim()
    if (!content || streaming) return

    setInput("")
    setStreaming(true)
    setStreamingText("")

    // 乐观插入 user 气泡(后端会落库,reload 时会拿到真实 id;turn 先标 -1)
    const optimisticUser: AgentConversationMessage = {
      id: -Date.now(),
      conversation_id: conversationId,
      role: "user",
      content,
      turn: (messages[messages.length - 1]?.turn ?? 0) + 1,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, optimisticUser])

    abortRef.current = new AbortController()
    let accumulated = ""
    try {
      await streamSSE(
        `/api/me/agent/conversations/${conversationId}/messages`,
        { content },
        {
          onToken: (tok) => {
            accumulated += tok
            setStreamingText(accumulated)
          },
          onError: (msg) => {
            setError(msg)
          },
          signal: abortRef.current.signal,
        },
      )
      // stream 结束后,把 streamingText 转成正式 assistant 气泡(暂用临时 id)
      if (accumulated) {
        const optimisticAssistant: AgentConversationMessage = {
          id: -Date.now() - 1,
          conversation_id: conversationId,
          role: "assistant",
          content: accumulated,
          turn: optimisticUser.turn + 1,
          created_at: new Date().toISOString(),
        }
        setMessages(prev => [...prev, optimisticAssistant])
      }
      setStreamingText("")
      // 后台 reload 一次拿真实 id(失败不影响)
      void loadMessages()
    } catch (e: any) {
      if (e?.name === "AbortError") {
        // 用户主动取消,流尾内容也保留到气泡
        if (accumulated) {
          setMessages(prev => [...prev, {
            id: -Date.now() - 1,
            conversation_id: conversationId,
            role: "assistant",
            content: accumulated + "\n[已取消]",
            turn: optimisticUser.turn + 1,
            created_at: new Date().toISOString(),
          }])
        }
      } else {
        setError(e?.detail || e?.message || "Agent 发送失败")
      }
    } finally {
      setStreaming(false)
      setStreamingText("")
      abortRef.current = null
      inputRef.current?.focus()
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter 发送,Shift+Enter 换行
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  function cancel() {
    abortRef.current?.abort()
  }

  return (
    <div className="flex flex-col h-full">
      {/* 消息流 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {loading && (
          <p className="text-center text-ink-secondary text-sm py-6">加载中…</p>
        )}

        {!loading && messages.length === 0 && !streaming && (
          <p className="text-center text-ink-tertiary text-sm py-6">
            还没说什么,你先开口 — 我在听。
          </p>
        )}

        {messages.map(m => (
          <Bubble key={m.id} role={m.role}>{m.content}</Bubble>
        ))}

        {streamingText && (
          <Bubble role="assistant" streaming>{streamingText}</Bubble>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 错误条 */}
      {error && (
        <div className="mx-4 mb-2 bg-warn-soft text-warn rounded-md px-3 py-2 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="underline ml-2">关掉</button>
        </div>
      )}

      {/* 输入区 */}
      <div className="border-t border-line-soft px-4 py-3 flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          rows={1}
          placeholder="跟你的 Agent 说点啥(Enter 发送,Shift+Enter 换行)"
          className="flex-1 resize-none border border-line-soft rounded-md px-3 py-2 text-sm focus:outline-none focus:border-primary max-h-32"
          disabled={streaming}
        />
        {streaming ? (
          <button
            onClick={cancel}
            className="bg-bg-soft text-ink-secondary border border-line-soft px-4 py-2 rounded-md text-sm hover:border-warn hover:text-warn transition"
          >
            停下
          </button>
        ) : (
          <button
            onClick={send}
            disabled={!input.trim()}
            className="bg-primary text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-primary-dark transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            发送
          </button>
        )}
      </div>
    </div>
  )
}

function Bubble({
  role,
  children,
  streaming,
}: {
  role: "user" | "assistant" | "system"
  children: React.ReactNode
  streaming?: boolean
}) {
  const isUser = role === "user"
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[82%] flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <span className="text-[11px] text-ink-tertiary px-1">
          {isUser ? "你" : "你的 Agent"}
          {streaming && <span className="ml-1.5 text-primary-dark">· 输入中…</span>}
        </span>
        <div className={`px-3.5 py-2.5 rounded-2xl text-[14px] leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-primary text-white rounded-br-sm"
            : "bg-bg-elevated border border-line-soft rounded-bl-sm"
        }`}>
          {children}
        </div>
      </div>
    </div>
  )
}
