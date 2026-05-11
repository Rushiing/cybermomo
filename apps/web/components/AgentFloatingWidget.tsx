"use client"

/**
 * 全站右下浮动 Agent · 一键打开"跟自己 Agent 聊"
 *
 * 行为:
 * - 全站可见(挂在 layout.tsx),onboarding / 登录页跳过
 * - 点击 → 抽屉弹出:展示最近一个 conversation,如果没有就创建一个 scope='general'
 * - 抽屉里嵌 AgentConversationView,关闭抽屉 stream 自动 abort
 * - 上方有按钮跳 /me/agent 看全部历史会话
 */
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import {
  api,
  type AgentConversation,
  type CreateAgentConversationRequest,
} from "@/lib/api"

import AgentConversationView from "./AgentConversationView"

const HIDE_PATH_PREFIXES = [
  "/onboarding",
  "/md/quiz",
  "/md/basic",
  "/md/review",
  "/md/generating",
  "/changelog",
]

function isHidden(pathname: string | null): boolean {
  if (!pathname) return true
  if (pathname === "/") return true
  return HIDE_PATH_PREFIXES.some(p => pathname.startsWith(p))
}

export default function AgentFloatingWidget() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [convId, setConvId] = useState<number | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (isHidden(pathname)) return null

  async function openWidget() {
    setOpen(true)
    setError(null)
    if (convId !== null) return  // 已经准备好了,直接展示

    setPreparing(true)
    try {
      // 先看有没有最近的 general/revisit/room conversation
      const list = await api.get<AgentConversation[]>("/api/me/agent/conversations")
      const recent = list[0]
      if (recent) {
        setConvId(recent.id)
      } else {
        // 没有任何会话 → 新建一个空的 general
        const conv = await api.post<AgentConversation, CreateAgentConversationRequest>(
          "/api/me/agent/conversations",
          { scope: "general" },
        )
        setConvId(conv.id)
      }
    } catch (e: any) {
      setError(e?.detail || e?.message || "无法打开 Agent")
    } finally {
      setPreparing(false)
    }
  }

  function close() {
    setOpen(false)
  }

  return (
    <>
      {/* 浮动按钮(右下,DEV 用户切换条上方 ~60px) */}
      <button
        onClick={openWidget}
        title="跟你的 Agent 聊"
        className="fixed bottom-16 right-5 z-40 w-12 h-12 rounded-full bg-primary text-white shadow-modal flex items-center justify-center hover:bg-primary-dark transition group"
      >
        <span className="relative flex items-center justify-center">
          <span className="block w-2.5 h-2.5 rounded-full bg-white" />
          <span className="absolute inset-[-6px] rounded-full border-[1.5px] border-white opacity-50 group-hover:opacity-80 animate-agent-pulse" />
        </span>
      </button>

      {/* 抽屉 */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end pointer-events-none">
          {/* 遮罩(可点关闭) */}
          <div
            className="absolute inset-0 bg-ink/30 backdrop-blur-sm pointer-events-auto"
            onClick={close}
          />

          {/* 右侧抽屉 */}
          <div className="relative bg-bg shadow-modal w-full max-w-md h-full flex flex-col pointer-events-auto">
            <header className="px-5 py-4 border-b border-line-soft flex items-center justify-between flex-shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <span className="relative">
                    <span className="block w-2 h-2 rounded-full bg-primary" />
                    <span className="absolute inset-[-3px] rounded-full border border-primary opacity-40 animate-agent-pulse" />
                  </span>
                  <h2 className="font-semibold text-base">你的 Agent</h2>
                </div>
                <p className="text-xs text-ink-tertiary mt-1">朋友式八卦,记得你最近的事</p>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href="/me/agent"
                  onClick={close}
                  className="text-xs text-ink-secondary hover:text-ink border border-line-soft hover:border-line rounded-full px-2.5 py-1 transition"
                >
                  全部会话
                </Link>
                <button
                  onClick={close}
                  className="w-8 h-8 rounded-md hover:bg-bg-soft flex items-center justify-center text-ink-secondary"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6L6 18M6 6l12 12"/>
                  </svg>
                </button>
              </div>
            </header>

            <div className="flex-1 overflow-hidden">
              {preparing && (
                <p className="text-center text-ink-secondary text-sm py-10">准备中…</p>
              )}
              {error && (
                <div className="m-4 bg-warn-soft text-warn rounded-md px-3 py-2 text-sm">
                  {error}
                  <button onClick={openWidget} className="underline ml-2">再试</button>
                </div>
              )}
              {!preparing && !error && convId !== null && (
                <AgentConversationView conversationId={convId} />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
