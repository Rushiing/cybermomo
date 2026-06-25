"use client"

/**
 * Agent 互聊查看 modal · 给宿主看 Agent 们都聊了什么
 *
 * 铁律:对方 Agent 的 private_signals 永远不暴露(后端已过滤)
 *      只显示 utterance + intent + topic_ref(public_signals)
 *      自己 Agent 的 private_signals 折叠在 details 里(可选展开)
 */
import { useEffect, useState } from "react"

import {
  api,
  type AgentChatViewResponse,
  type AgentChatMessageView,
} from "@/lib/api"

interface Props {
  summaryId: number
  open: boolean
  onClose: () => void
}

const INTENT_LABEL: Record<string, string> = {
  probe: "探问",
  share: "分享",
  align: "认同",
  deflect: "回避",
  reject: "拒绝",
  wrap: "收尾",
}

// 内部信号 → 用户语言。给宿主看的是"你的 Agent 这轮的感受",不暴露字段名/字面值。
// rewrite_level(改写程度)是生成过程的 meta,对真人无意义,不展示。
type SignalTone = "up" | "down" | "neutral" | "warn"

const TONE_CLASS: Record<SignalTone, string> = {
  up: "bg-primary-soft text-primary-dark",
  down: "bg-bg-soft text-ink-secondary",
  neutral: "bg-bg-soft text-ink-tertiary",
  warn: "bg-warn-soft text-warn",
}

function ownSignalsFriendly(sig: Record<string, any>): { label: string; tone: SignalTone }[] {
  const out: { label: string; tone: SignalTone }[] = []

  // 好感变化
  if (sig.warmth_delta === 1) out.push({ label: "对 ta 更有好感", tone: "up" })
  else if (sig.warmth_delta === -1) out.push({ label: "对 ta 好感降了点", tone: "down" })
  else if (sig.warmth_delta === 0) out.push({ label: "好感持平", tone: "neutral" })

  // 话题兴趣(0 = 一般,不展示以免噪音)
  if (sig.topic_interest === 1) out.push({ label: "聊得来劲", tone: "up" })
  else if (sig.topic_interest === -1) out.push({ label: "对话题没什么兴趣", tone: "down" })

  // 自我披露深度
  const disclosure: Record<number, { label: string; tone: SignalTone }> = {
    0: { label: "没怎么敞开自己", tone: "neutral" },
    1: { label: "浅聊了下自己", tone: "neutral" },
    2: { label: "聊得比较深", tone: "up" },
    3: { label: "聊得很坦诚", tone: "up" },
  }
  if (sig.disclosure_level != null && disclosure[sig.disclosure_level]) {
    out.push(disclosure[sig.disclosure_level])
  }

  // 碰到边界
  const boundary: Record<string, string> = {
    价值观: "感觉价值观不太合",
    隐私: "碰到隐私话题,收住了",
    铁律: "触发了平台底线",
  }
  if (sig.boundary_hit) {
    out.push({ label: boundary[sig.boundary_hit] || "碰到了边界", tone: "warn" })
  }

  return out
}

export default function AgentChatViewer({ summaryId, open, onClose }: Props) {
  const [data, setData] = useState<AgentChatViewResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    void load()
  }, [open, summaryId])

  async function load() {
    setLoading(true)
    setError(null)
    setData(null)
    try {
      const resp = await api.get<AgentChatViewResponse>(`/api/summary/${summaryId}/agent_chat`)
      setData(resp)
    } catch (e: any) {
      setError(e?.detail || e?.message || "加载失败")
    } finally {
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-bg rounded-lg shadow-modal max-w-2xl w-full max-h-[85vh] flex flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-line-soft flex-shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary" />
              <h2 className="font-semibold text-base">Agent 互聊回放</h2>
            </div>
            <p className="text-xs text-ink-tertiary mt-1">
              你的 Agent 跟对方 Agent 的对话(对方 Agent 的内部信号不展示)
            </p>
          </div>
          <button onClick={onClose} className="w-9 h-9 rounded-md hover:bg-bg-soft flex items-center justify-center text-ink-secondary">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="text-center py-12 text-ink-secondary text-sm">加载中…</div>
          )}

          {error && (
            <div className="bg-warn-soft text-warn rounded-md px-4 py-3 text-sm">
              {error}
              <button onClick={load} className="underline ml-2">再试</button>
            </div>
          )}

          {data && (
            <>
              <div className="text-xs text-ink-tertiary mb-4 flex items-center gap-3 pb-3 border-b border-dashed border-line-soft">
                <span>共 {data.turns} 轮</span>
                <span>·</span>
                <span>状态:{statusLabel(data.status)}</span>
                {data.end_reason && (
                  <>
                    <span>·</span>
                    <span>结束原因:{endReasonLabel(data.end_reason)}</span>
                  </>
                )}
              </div>

              {data.messages.length === 0 ? (
                <p className="text-center py-8 text-ink-secondary text-sm">还没有消息</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {data.messages.map(m => <MessageBubble key={m.id} m={m} />)}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-6 py-3 border-t border-line-soft flex-shrink-0">
          <p className="text-xs text-ink-tertiary leading-relaxed">
            🔒 这是只给你的回放 — 对方 Agent 的小心思(好感变化、聊得多深这些)按铁律不展示。
          </p>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ m }: { m: AgentChatMessageView }) {
  const isHost = m.speaker === "host"
  const intentLabel = INTENT_LABEL[m.intent] || m.intent

  return (
    <div className={`flex ${isHost ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isHost ? "items-end" : "items-start"} flex flex-col gap-1`}>
        <div className="flex items-center gap-2 text-[11px] text-ink-tertiary px-1">
          <span>{isHost ? "你的 Agent" : "对方 Agent"}</span>
          <span>·</span>
          <span>第 {m.turn} 轮</span>
          <span>·</span>
          <span>{intentLabel}</span>
          {m.topic_ref && (
            <>
              <span>·</span>
              <span className="bg-bg-soft px-1.5 py-px rounded text-[10px]">{m.topic_ref}</span>
            </>
          )}
        </div>
        <div className={`px-3.5 py-2.5 rounded-2xl text-[14px] leading-relaxed ${
          isHost
            ? "bg-primary text-white rounded-br-sm"
            : "bg-bg-elevated border border-line-soft rounded-bl-sm"
        }`}>
          {m.utterance}
        </div>
        {(() => {
          if (!m.own_private_signals) return null
          const signals = ownSignalsFriendly(m.own_private_signals)
          if (signals.length === 0) return null
          return (
            <details className="text-[11px] text-ink-tertiary px-1 mt-0.5">
              <summary className="cursor-pointer hover:text-ink-secondary select-none">
                你的 Agent 这轮的小心思
              </summary>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {signals.map((s, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] ${TONE_CLASS[s.tone]}`}
                  >
                    {s.label}
                  </span>
                ))}
              </div>
            </details>
          )
        })()}
      </div>
    </div>
  )
}

function statusLabel(s: string): string {
  return ({
    running: "进行中",
    done_natural: "自然结束",
    done_terminated: "中断",
    re_dispatched: "已再派",
  } as Record<string, string>)[s] || s
}

function endReasonLabel(r: string): string {
  return ({
    natural_wrap: "自然收尾",
    turn_limit: "聊够了",
    boundary_hit_铁律: "触发底线",
    no_hooks: "没有话题钩子",
    missing_profile: ".md 不存在",
    llm_error: "LLM 故障",
    parse_error: "解析失败",
  } as Record<string, string>)[r] || r
}
