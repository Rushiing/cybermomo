"use client"

/**
 * 屏 9 · .md 完成 + 自我审阅
 *
 * 优先从 API 拉(GET /api/md/me),失败时 fallback 到 localStorage(刚答完的本地 profile)。
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { api, type MdDocumentResponse } from "@/lib/api"
import type { Profile } from "@/lib/v3"

interface DisplayData {
  title: string
  body: string[]
  domains_interested: string[]
  domains_avoided: string[]
  // 可选:portrait.tags / core_tension
  tags?: string[]
  core_tension?: string
}

export default function ReviewPage() {
  const router = useRouter()
  const [data, setData] = useState<DisplayData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<MdDocumentResponse>("/api/md/me")
      setData({
        title: res.portrait_title,
        body: res.portrait_body || [],
        domains_interested: res.domains_interested || [],
        domains_avoided: res.domains_avoided || [],
      })
    } catch (e: any) {
      // 可能后端还没创建,fallback 到 localStorage 的 profile
      try {
        const raw = localStorage.getItem("cybermomo_profile")
        if (raw) {
          const profile = JSON.parse(raw) as Profile
          setData({
            title: profile.portrait?.title || "档案生成失败",
            body: profile.portrait?.body || [],
            domains_interested: profile.domains?.interested || [],
            domains_avoided: profile.domains?.avoided || [],
            tags: profile.portrait?.tags || [],
            core_tension: profile.portrait?.core_tension,
          })
          return
        }
      } catch { /* ignore */ }
      setError(e?.detail || e?.message || "加载档案失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* 铁律 hint banner */}
      <div className="bg-primary-soft border-b border-primary/[.18] px-8 py-3.5">
        <div className="max-w-[760px] mx-auto flex items-center gap-3 text-primary-dark text-[13px] leading-relaxed">
          <span>🔒</span>
          <span>这是给你 Agent 的人格档案。<strong className="font-semibold">只你能看到</strong>,任何其他用户都看不到原文。</span>
        </div>
      </div>

      <main className="flex-1 max-w-[760px] mx-auto w-full px-6 py-9 pb-32">
        {loading && (
          <div className="text-center py-16 text-ink-secondary">加载中…</div>
        )}
        {error && (
          <div className="text-center py-16">
            <p className="text-warn mb-3">{error}</p>
            <button onClick={() => loadData()} className="text-primary underline">再试</button>
          </div>
        )}
        {data && (
          <>
            <div className="text-[13px] text-ink-secondary uppercase tracking-[0.08em] mb-2">你的人格档案</div>
            <h1 className="text-[26px] font-semibold leading-tight mb-5 text-primary-dark">{data.title}</h1>

            {data.tags && data.tags.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-7">
                {data.tags.map((t, i) => (
                  <span key={i} className={`text-[12.5px] rounded-full px-3 py-1.5 border ${
                    i < 5 ? "bg-primary-soft border-primary/30 text-primary-dark font-medium" : "bg-bg-elevated border-line-soft text-ink-secondary"
                  }`}>{t}</span>
                ))}
              </div>
            )}

            {data.core_tension && (
              <div className="bg-primary-soft border-l-[3px] border-primary rounded-md px-4 py-3.5 text-primary-dark font-medium mb-6 leading-relaxed">
                <div className="text-[11.5px] font-semibold opacity-80 tracking-[0.04em] mb-1">核心张力</div>
                {data.core_tension}
              </div>
            )}

            <article className="bg-bg-elevated border border-line-soft rounded-md px-8 py-7 shadow-card mb-6">
              {data.body.map((p, i) => (
                <p key={i} className={`mb-3.5 leading-relaxed ${
                  i === 0 ? "text-sm text-ink-secondary pb-3.5 border-b border-dashed border-line-soft"
                  : "text-[15px] text-ink"
                }`}>
                  {p}
                </p>
              ))}
            </article>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
              <div className="bg-bg-elevated border border-line-soft rounded-md px-4 py-4">
                <h3 className="text-xs text-ink-secondary mb-2 tracking-[0.04em]">主动会逛的</h3>
                <div className="flex flex-wrap gap-1.5">
                  {data.domains_interested.length === 0
                    ? <span className="bg-bg-soft text-ink-secondary opacity-50 italic rounded-full px-2.5 py-0.5 text-xs">没填</span>
                    : data.domains_interested.map(d => (
                      <span key={d} className="bg-bg-soft text-ink rounded-full px-2.5 py-0.5 text-xs">{d}</span>
                    ))}
                </div>
              </div>
              <div className="bg-bg-elevated border border-line-soft rounded-md px-4 py-4">
                <h3 className="text-xs text-ink-secondary mb-2 tracking-[0.04em]">主动回避的</h3>
                <div className="flex flex-wrap gap-1.5">
                  {data.domains_avoided.length === 0
                    ? <span className="bg-bg-soft text-ink-secondary opacity-50 italic rounded-full px-2.5 py-0.5 text-xs">没填</span>
                    : data.domains_avoided.map(d => (
                      <span key={d} className="bg-bg-soft text-ink rounded-full px-2.5 py-0.5 text-xs">{d}</span>
                    ))}
                </div>
              </div>
            </div>
          </>
        )}
      </main>

      <footer className="fixed bottom-0 left-0 right-0 bg-bg border-t border-line-soft px-8 py-3.5 z-40">
        <div className="max-w-[760px] mx-auto flex items-center justify-between">
          <span className="text-xs text-ink-secondary">读完了之后,你的 Agent 就开始替你认识人了。</span>
          <Link href="/room" className="bg-primary text-white px-7 py-3 rounded-full font-medium hover:bg-primary-dark transition">
            进个人房间 →
          </Link>
        </div>
      </footer>
    </div>
  )
}
