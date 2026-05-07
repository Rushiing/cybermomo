"use client"

/**
 * 屏 16 · 真人聊天前 Agent 简报(§4.9)
 *
 * 用户决策开聊后必经的页面。
 * GET /api/chat/sessions/{id}/briefing
 */
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { api, type ChatBriefingResponse } from "@/lib/api"

export default function BriefingPage({ params }: { params: { sessionId: string } }) {
  const router = useRouter()
  const sessionId = params.sessionId
  const [data, setData] = useState<ChatBriefingResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void load()
  }, [sessionId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.get<ChatBriefingResponse>(`/api/chat/sessions/${sessionId}/briefing`)
      setData(resp)
    } catch (e: any) {
      setError(e?.detail || e?.message || "简报生成失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-bg border-b border-line-soft px-8 py-4 flex items-center gap-4">
        <button onClick={() => router.back()} className="w-9 h-9 rounded-md hover:bg-bg-soft flex items-center justify-center">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>
          </svg>
        </button>
        <div className="text-sm text-ink-secondary">
          <strong className="font-medium text-ink">真人聊天前的简报</strong> · 跟对方聊之前,先听 Agent 跟你交个底
        </div>
      </header>

      <main className="flex-1 max-w-[640px] mx-auto w-full px-8 py-10 pb-32">
        <div className="flex items-center gap-3 mb-7">
          <div className="relative flex-shrink-0">
            <span className="block w-3 h-3 rounded-full bg-primary" />
            <span className="absolute inset-[-4px] rounded-full border-[1.5px] border-primary opacity-40 animate-agent-pulse" />
          </div>
          <div>
            <div className="font-semibold text-sm">你的 Agent</div>
            <div className="text-xs text-ink-secondary">把刚才跟对方聊的精华给你交个底</div>
          </div>
        </div>

        <h1 className="text-[22px] font-semibold leading-snug mb-3">跟你简单同步下我跟 TA 聊的</h1>
        <p className="text-sm text-ink-secondary mb-9">读完之后再决定要不要开聊。<strong className="text-ink font-medium">这里说的我都说过</strong>,真人对话起来对方可能会提到。</p>

        {loading && <p className="text-center py-12 text-ink-secondary">Agent 正在整理跟 TA 聊过的内容…(可能要几秒)</p>}

        {error && (
          <div className="bg-warn-soft text-warn rounded-md px-4 py-3.5 text-sm">
            {error} <button onClick={() => load()} className="underline ml-2">再试</button>
          </div>
        )}

        {data && (
          <>
            <div className="bg-bg-elevated border border-line-soft rounded-md px-8 py-7 shadow-card mb-6">
              {data.highlights.map((h, i) => (
                <p key={i} className="mb-3.5 last:mb-0 text-[15.5px] leading-loose">
                  {h.text}
                </p>
              ))}
            </div>

            {data.risks.length > 0 && (
              <div className="bg-bg-elevated border border-line-soft rounded-md px-8 py-5 mb-6">
                <div className="text-xs text-ink-secondary mb-2 tracking-[0.04em]">需要留意</div>
                {data.risks.map((r, i) => (
                  <p key={i} className="text-sm text-ink leading-relaxed mb-2 last:mb-0 pl-3 border-l-2 border-warn-soft">
                    {r.text}
                  </p>
                ))}
              </div>
            )}

            <div className="bg-bg-elevated border border-dashed border-line rounded-md px-5 py-4 text-sm text-ink-secondary leading-relaxed">
              真人聊天里 TA 不会看见我,但我还在 — 输入框旁有我的图标,你需要时随时叫我。
            </div>
          </>
        )}
      </main>

      <footer className="fixed bottom-0 left-0 right-0 bg-bg border-t border-line-soft px-8 py-4">
        <div className="max-w-[640px] mx-auto flex items-center justify-between gap-4">
          <button onClick={() => router.back()} className="border-[1.5px] border-line text-ink px-7 py-3 rounded-full hover:border-ink-secondary transition font-medium text-sm">
            再想想
          </button>
          <button
            onClick={() => router.push(`/chat/${sessionId}`)}
            disabled={!data}
            className="bg-primary text-white px-7 py-3 rounded-full font-medium hover:bg-primary-dark disabled:opacity-40 transition"
          >
            好,去聊吧 →
          </button>
        </div>
      </footer>
    </div>
  )
}
