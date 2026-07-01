"use client"

/**
 * 屏 2-5 · Onboarding 告知屏(4 屏内部切换 + 18 岁 gate)
 *
 * 文案严格按 vault/落地拆解/01-用户注册/Onboarding告知屏-文案-v0.md
 * 完成后跳 /md/basic
 */
import { useRouter } from "next/navigation"
import { useState } from "react"

const SCREENS = [
  {
    title: "在这里,先聊的不是你",
    paragraphs: [
      "这个平台上每个人都有一个 AI 分身,叫 Agent。",
      "你和别人的第一次接触,是你们的 Agent 之间互聊。",
      <span key="bold"><strong className="font-medium">你看到的是简报,你决定要不要亲自上。</strong></span>,
    ],
  },
  {
    title: "你的 .md 决定你的 Agent",
    paragraphs: [
      "接下来我们会用一组问题给你生成一份 .md。",
      "这份 .md = 你的 Agent 的人格说明书。",
    ],
    strongLine: "你可以自己查看,你的 Agent 会使用它;其他用户永远看不到原文。",
  },
  {
    title: "你管 Agent,但管不死 ta",
    paragraphs: [
      "你能给 Agent 调方向、出话题、提建议。",
      "但 ta 有自己的脾气,可能不全听你的。",
      <span key="bold"><strong className="font-medium">"开聊 / 不聊"的最终按钮永远在你手上。</strong></span>,
    ],
  },
  {
    title: "几条提前说清楚的",
    list: [
      <span key="1">平台<strong className="font-medium">不会主动</strong>给你推消息、推荐、催你上线</span>,
      <span key="2">你提交的信息真实性由你自负,平台不替你背书</span>,
      <span key="3">你随时可以注销,.md 和聊天记录一起删干净</span>,
      <span key="4">你必须年满 <strong className="font-medium">18 岁</strong></span>,
    ],
    requiresAdult: true,
  },
]

export default function OnboardingPage() {
  const router = useRouter()
  const [current, setCurrent] = useState(0)
  const [adultChecked, setAdultChecked] = useState(false)

  const screen = SCREENS[current]
  const isLast = current === SCREENS.length - 1
  const canProceed = !screen.requiresAdult || adultChecked

  function next() {
    if (isLast) {
      if (!canProceed) return
      router.push("/md/basic")
    } else {
      setCurrent(current + 1)
    }
  }

  function back() {
    if (current > 0) setCurrent(current - 1)
  }

  function skip() {
    setCurrent(SCREENS.length - 1)
  }

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      {/* 顶部 - 跳过 */}
      <div className="px-8 py-6 flex justify-end">
        {!isLast && (
          <button onClick={skip} className="text-sm text-ink-tertiary hover:text-ink-secondary transition">
            跳过
          </button>
        )}
      </div>

      {/* 主舞台 */}
      <main className="flex-1 flex items-center justify-center px-8">
        <section className="max-w-[560px] w-full animate-fade-in" key={current}>
          <h1 className="text-[28px] font-semibold tracking-tight mb-6 leading-tight">{screen.title}</h1>

          {screen.paragraphs?.map((p, i) => (
            <p key={i} className="text-base leading-loose mb-4 text-ink">{p}</p>
          ))}

          {screen.strongLine && (
            <div className="bg-primary-soft border-l-[3px] border-primary rounded-md px-4 py-3 mt-2 font-medium text-primary-dark leading-relaxed">
              {screen.strongLine}
            </div>
          )}

          {screen.list && (
            <ul className="space-y-3 mt-2">
              {screen.list.map((item, i) => (
                <li key={i} className="text-[15.5px] text-ink py-3 border-b border-dashed border-line-soft last:border-b-0">
                  {item}
                </li>
              ))}
            </ul>
          )}

          {screen.requiresAdult && (
            <button
              onClick={() => setAdultChecked(!adultChecked)}
              className={`flex items-center gap-2.5 p-4 mt-8 w-full bg-bg-elevated border-[1.5px] rounded-md transition text-left ${
                adultChecked ? "border-primary" : "border-line-soft hover:border-ink-secondary"
              }`}
            >
              <span className={`w-5 h-5 rounded flex items-center justify-center flex-shrink-0 transition ${
                adultChecked ? "bg-primary" : "border-[1.5px] border-line"
              }`}>
                {adultChecked && (
                  <svg width="12" height="9" viewBox="0 0 12 9" fill="none">
                    <path d="M1 4.5L4.5 8L11 1" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
              </span>
              <span className="text-[15px]">我已年满 18 岁</span>
            </button>
          )}
        </section>
      </main>

      {/* 底部进度 + 按钮 */}
      <div className="px-8 pt-6 pb-10">
        <div className="max-w-[560px] mx-auto flex items-center justify-between gap-4">
          <button
            onClick={back}
            className={`text-sm text-ink-secondary hover:text-ink transition ${current === 0 ? "invisible" : ""}`}
          >
            ← 上一步
          </button>
          <div className="flex gap-2">
            {SCREENS.map((_, i) => (
              <div key={i} className={`h-1.5 rounded-full transition-all ${
                i === current ? "w-6 bg-primary" : "w-1.5 bg-line"
              }`} />
            ))}
          </div>
          <button
            onClick={next}
            disabled={!canProceed}
            className={`px-7 py-3 rounded-full text-sm font-medium transition ${
              isLast
                ? "bg-primary text-white hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed"
                : "bg-ink text-bg hover:bg-[#111827] hover:-translate-y-px"
            }`}
          >
            {isLast ? "我懂了,开始建 .md" : "下一步"}
          </button>
        </div>
      </div>
    </div>
  )
}
