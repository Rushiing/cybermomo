"use client"

/**
 * 屏 7 · 灵魂快照 17 题 + 领域预设
 *
 * 完成后:前端跑规则引擎 → POST /api/md → 跳 /md/generating
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useMemo, useState } from "react"

import { api, type CreateMdRequest, type MdDocumentResponse } from "@/lib/api"
import { AREAS, Q, buildProfile } from "@/lib/v3"

export default function QuizPage() {
  const router = useRouter()
  const [stage, setStage] = useState<"intro" | "preset" | "quiz">("intro")
  const [p1, setP1] = useState<Set<string>>(new Set())
  const [p2, setP2] = useState<Set<string>>(new Set())
  const [idx, setIdx] = useState(0)
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const totalQ = Q.length
  const progress = stage === "intro" ? 0 : stage === "preset" ? 5 : ((idx + 1) / totalQ) * 100

  // ---- 领域预设 ----
  function toggleP1(area: string) {
    const next = new Set(p1)
    if (next.has(area)) next.delete(area)
    else { next.add(area); const np2 = new Set(p2); np2.delete(area); setP2(np2) }
    setP1(next)
  }
  function toggleP2(area: string) {
    if (p1.has(area)) return
    const next = new Set(p2)
    if (next.has(area)) next.delete(area)
    else next.add(area)
    setP2(next)
  }

  // ---- 答题 ----
  function pickOption(optIdx: number) {
    // 注:外层 idx 是当前题号(state),这里取当前题的 id 作 key
    const qid = Q[idx].id
    setAnswers(prev => ({ ...prev, [qid]: optIdx }))
  }

  function next() {
    if (answers[Q[idx].id] === undefined) return
    if (idx < totalQ - 1) setIdx(idx + 1)
    else void submit()
  }
  function prev() { if (idx > 0) setIdx(idx - 1) }

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      const profile = buildProfile({
        answers,
        domains: { interested: Array.from(p1), avoided: Array.from(p2) },
      })
      // 存 localStorage(给 /md/review 用作 fallback,如果 API 失败仍能展示)
      try {
        localStorage.setItem("cybermomo_profile", JSON.stringify(profile))
      } catch { /* ignore */ }

      const body: CreateMdRequest = { profile }
      const res = await api.post<MdDocumentResponse, CreateMdRequest>("/api/md", body)
      try {
        localStorage.setItem("cybermomo_md_id", String(res.id))
      } catch { /* ignore */ }
      router.push("/md/generating")
    } catch (e: any) {
      console.error(e)
      setError(e?.detail || e?.message || "提交失败")
      setSubmitting(false)
    }
  }

  const currentQ = Q[idx]
  const currentSel = currentQ ? answers[currentQ.id] : undefined

  return (
    <div className="min-h-screen flex flex-col">
      {/* 顶部 progress */}
      <header className="sticky top-0 z-20 bg-bg/90 backdrop-blur border-b border-line-soft">
        <div className="max-w-[980px] mx-auto px-5 py-3.5 flex items-center gap-4 justify-between">
          <div className="font-semibold flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-primary" />
            CyberMOMO · 灵魂快照
          </div>
          <div className="flex-1 max-w-[460px] h-1.5 bg-line-soft rounded-full overflow-hidden">
            <div className="h-full bg-primary transition-[width] duration-200" style={{ width: `${progress}%` }} />
          </div>
          <div className="text-[13px] text-ink-secondary min-w-[82px] text-right tabular-nums">
            {stage === "intro" ? "开始" : stage === "preset" ? "领域预设" : `${idx + 1} / ${totalQ}`}
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-[980px] w-full mx-auto px-5 py-7 pb-32">
        {stage === "intro" && (
          <section className="bg-bg-elevated border border-line-soft rounded-lg shadow-card p-7">
            <h1 className="text-[28px] font-semibold leading-tight mb-2 tracking-tight">灵魂快照 · 17 题 + 领域</h1>
            <p className="text-ink-secondary mb-3">17 道场景题 + 2 道领域题,生成你的 Agent 人格档案。慢慢来,我会认真读你的回答。</p>
            <p className="text-ink-tertiary text-sm">这份档案你可以自己查看,也会交给你的 Agent 使用。任何其他用户都看不到原文。</p>
            <div className="mt-6">
              <button onClick={() => setStage("preset")} className="bg-primary text-white px-6 py-3 rounded-md font-medium hover:bg-primary-dark transition">
                开始 →
              </button>
            </div>
          </section>
        )}

        {stage === "preset" && (
          <section className="bg-bg-elevated border border-line-soft rounded-lg shadow-card p-7">
            <h2 className="text-primary-dark font-semibold mb-4">Step 0 · 领域预设</h2>

            <h3 className="text-lg font-semibold mb-2">你平时主动会逛的领域</h3>
            <p className="text-sm text-ink-secondary mb-3">可多选,可空选,不限制数量。</p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2 mb-6">
              {AREAS.map(a => (
                <button
                  key={a}
                  onClick={() => toggleP1(a)}
                  className={`border-[1.5px] rounded-full px-3 py-2 text-[13.5px] transition ${
                    p1.has(a) ? "bg-primary-soft border-primary text-primary-dark font-medium" : "border-line-soft hover:border-primary"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>

            <h3 className="text-lg font-semibold mb-2 mt-7">你会主动回避或反感的领域</h3>
            <p className="text-sm text-ink-secondary mb-3">可多选,可空选,不限制数量。已选感兴趣的领域不会出现在这里。</p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2">
              {AREAS.map(a => (
                <button
                  key={a}
                  onClick={() => toggleP2(a)}
                  disabled={p1.has(a)}
                  className={`border-[1.5px] rounded-full px-3 py-2 text-[13.5px] transition ${
                    p1.has(a) ? "opacity-30 cursor-not-allowed border-line-soft"
                    : p2.has(a) ? "bg-primary-soft border-primary text-primary-dark font-medium"
                    : "border-line-soft hover:border-primary"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3 mt-6 flex-wrap">
              <button onClick={() => setStage("quiz")} className="bg-primary text-white px-6 py-3 rounded-md font-medium hover:bg-primary-dark transition">
                开始正式题 →
              </button>
              <span className="text-sm text-ink-secondary">已选感兴趣:{p1.size};主动回避:{p2.size}</span>
            </div>
          </section>
        )}

        {stage === "quiz" && currentQ && (
          <section className="bg-bg-elevated border border-line-soft rounded-lg shadow-card p-7 animate-fade-in">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div className="text-[13px] text-primary font-semibold">第 {idx + 1} 题 / {totalQ}</div>
              <div className="text-xs text-ink-tertiary font-medium">{currentQ.id}</div>
            </div>
            <h3 className="text-[22px] font-semibold leading-snug mb-4">{currentQ.title}</h3>
            <div className="text-base whitespace-pre-line mb-3.5">{currentQ.text}</div>
            {currentQ.note && (
              <div className="text-ink-secondary bg-bg-soft border-l-[3px] border-line rounded-md px-3.5 py-3 text-[13.5px] leading-relaxed mb-4 whitespace-pre-line">
                {currentQ.note}
              </div>
            )}

            <div className="grid gap-2.5 mt-5">
              {currentQ.options.map((opt, j) => (
                <button
                  key={j}
                  onClick={() => pickOption(j)}
                  className={`flex items-start gap-3 w-full text-left border-[1.5px] rounded-md px-4 py-3.5 text-[15px] leading-relaxed transition font-[inherit] ${
                    currentSel === j
                      ? "border-primary bg-primary-soft text-primary-dark font-medium shadow-[0_0_0_3px_rgba(0,174,66,0.12)]"
                      : "bg-bg-elevated border-line-soft hover:border-primary hover:bg-primary-soft"
                  }`}
                >
                  <span className={`flex-shrink-0 w-7 h-7 rounded-full inline-flex items-center justify-center font-semibold text-[13px] ${
                    currentSel === j ? "bg-primary text-white" : "bg-bg-soft text-ink-secondary"
                  }`}>
                    {j + 1}
                  </span>
                  <span>{opt}</span>
                </button>
              ))}
            </div>

            {error && (
              <div className="mt-4 px-4 py-3 bg-warn-soft text-warn rounded-md text-sm">
                {error} — <button onClick={() => void submit()} className="underline">再试一次</button>
              </div>
            )}

            <div className="flex gap-3 justify-between mt-7">
              <button onClick={prev} disabled={idx === 0} className="bg-bg-soft text-ink px-5 py-3 rounded-md font-medium hover:bg-line transition disabled:opacity-45 disabled:cursor-not-allowed">
                上一题
              </button>
              <button
                onClick={next}
                disabled={currentSel === undefined || submitting}
                className="bg-primary text-white px-6 py-3 rounded-md font-medium hover:bg-primary-dark transition disabled:opacity-45 disabled:cursor-not-allowed"
              >
                {submitting ? "提交中…" : idx === totalQ - 1 ? "提交,生成画像 →" : "下一题"}
              </button>
            </div>
          </section>
        )}
      </main>

      <footer className="fixed bottom-0 left-0 right-0 border-t border-line-soft bg-bg/90 backdrop-blur px-5 py-3 text-center">
        <Link href="/" className="text-xs text-ink-tertiary hover:text-ink">← 回到登录</Link>
      </footer>
    </div>
  )
}
