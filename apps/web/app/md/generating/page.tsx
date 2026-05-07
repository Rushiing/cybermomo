"use client"

/**
 * 屏 8 · 生成等待
 *
 * v3 是前端规则引擎产出,实际已经生成完毕(< 100ms)。
 * 这屏只是过场感,2.5s 后跳到 review。
 */
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

const LINES = [
  "嗯…让我把你刚才答的过一遍。",
  "你这种节奏的味道,我有数了。",
  "几个细节我得回味一下,马上好。",
]

export default function GeneratingPage() {
  const router = useRouter()
  const [shown, setShown] = useState(0)
  const [pct, setPct] = useState(10)

  useEffect(() => {
    const t1 = setTimeout(() => setShown(1), 400)
    const t2 = setTimeout(() => setShown(2), 1100)
    const t3 = setTimeout(() => setShown(3), 1900)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [])

  useEffect(() => {
    const interval = setInterval(() => {
      setPct(p => Math.min(100, p + 4))
    }, 80)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (pct >= 100) {
      const t = setTimeout(() => router.push("/md/review"), 400)
      return () => clearTimeout(t)
    }
  }, [pct, router])

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-8 py-10 bg-gradient-to-br from-bg via-bg to-[#efe7db]">
      <div className="relative w-[18px] h-[18px] mb-6">
        <span className="block w-full h-full rounded-full bg-primary shadow-[0_0_0_8px_rgba(0,174,66,0.10)]" />
        <span className="absolute inset-[-8px] rounded-full border-[1.5px] border-primary opacity-40 animate-agent-pulse" />
      </div>
      <div className="text-xs text-ink-secondary tracking-[0.04em] mb-4">你的 Agent</div>

      <div className="max-w-[480px] text-center mb-12 min-h-[100px]">
        {LINES.map((line, i) => (
          <div
            key={i}
            className={`text-[17px] leading-relaxed mb-2 transition-all duration-500 ${
              i < shown ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
            }`}
          >
            {line}
          </div>
        ))}
      </div>

      <div className="w-full max-w-[320px] flex flex-col items-center gap-3">
        <div className="w-full h-[3px] bg-primary/[.12] rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full transition-[width] duration-500" style={{ width: `${pct}%` }} />
        </div>
        <div className="text-xs text-ink-tertiary">{pct >= 95 ? "快好了…" : "正在生成你的人格档案…"}</div>
      </div>
    </main>
  )
}
