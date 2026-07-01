"use client"

/**
 * 屏 13-14 · 个人房间(主屏 + 简报卡详情 + 真人聊天入口)
 *
 * 拉:
 *   - GET /api/room/status         状态栏数据
 *   - GET /api/summary/me          简报列表
 *   - GET /api/chat/sessions/me    真人聊天 session 列表(active 的进入入口)
 *
 * 决策(开聊/再派/丢/调方向)POST /api/summary/{id}/decision。
 */
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import AgentChatViewer from "@/components/AgentChatViewer"
import Topbar from "@/components/Topbar"
import {
  api,
  type ChatSessionResponse,
  type DecisionRequest,
  type RoomStatusResponse,
  type SummaryResponse,
  getMockUserId,
} from "@/lib/api"

type Verdict = "来电" | "不合" | "有点意思再观察" | string

function verdictColor(v: Verdict): string {
  if (v === "来电" || v.includes("来电(")) return "text-primary"
  if (v === "不合" || v.includes("不合(")) return "text-ink-tertiary"
  return "text-ink"
}

export default function RoomPage() {
  const router = useRouter()
  const [status, setStatus] = useState<RoomStatusResponse | null>(null)
  const [summaries, setSummaries] = useState<SummaryResponse[]>([])
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([])
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionPending, setActionPending] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [viewerSummaryId, setViewerSummaryId] = useState<number | null>(null)
  const [focusedSummaryId, setFocusedSummaryId] = useState<number | null>(null)

  const myUid = Number(getMockUserId())

  useEffect(() => {
    void loadAll()
    // 用户刚 onboarding 完进 /room 时,后台 pipeline 大概率还在跑(实测
    // ~6-8 分钟跑完 5 match × ~11 LLM call)。POST /api/md 触发的 BackgroundTask
    // fire-and-forget,前端没法精准等 — 用 polling 自动刷新,5 分钟超时停。
    //
    // 30s 间隔在"顺滑"和"开销"之间平衡:loadAll 3 个轻 SQL 并发 ~300ms。
    const startedAt = Date.now()
    const POLL_INTERVAL_MS = 30_000
    const POLL_DEADLINE_MS = 5 * 60_000
    const id = setInterval(() => {
      if (Date.now() - startedAt > POLL_DEADLINE_MS) {
        clearInterval(id)
        return
      }
      void loadAll({ silent: true })
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 5000)
    return () => clearTimeout(t)
  }, [notice])
  useEffect(() => {
    if (loading || summaries.length === 0 || typeof window === "undefined") return
    const focus = Number(new URLSearchParams(window.location.search).get("focus"))
    if (!focus || focusedSummaryId === focus) return
    if (!summaries.some(s => s.id === focus)) return
    setFocusedSummaryId(focus)
    jumpToBriefing(focus)
  }, [loading, summaries, focusedSummaryId])

  async function loadAll(opts?: { silent?: boolean }) {
    // silent:轮询 / 决策后的补刷不弹整页"加载中",只首屏 load 显 spinner
    if (!opts?.silent) setLoading(true)
    try {
      const [s, sums, ss] = await Promise.all([
        api.get<RoomStatusResponse>("/api/room/status"),
        api.get<SummaryResponse[]>("/api/summary/me"),
        api.get<ChatSessionResponse[]>("/api/chat/sessions/me"),
      ])
      setStatus(s)
      setSummaries(sums)
      setSessions(ss)
    } catch (e: any) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function decide(summaryId: number, decision: DecisionRequest["decision"]) {
    setActionPending(summaryId)
    // 乐观更新:丢 / 再派 点下去立刻把卡片翻成"已决策",点击零延迟感;
    // 服务端 decision POST 在后台跑(Railway 上 ~几秒),失败再回滚。
    // open_human_chat 不乐观 —— 它成功要带服务端建的 session 跳走,等返回更稳妥。
    const snapshot = summaries
    if (decision === "drop" || decision === "re_dispatch") {
      setSummaries(prev => prev.map(s =>
        s.id === summaryId ? { ...s, user_decision: decision } : s
      ))
    }
    try {
      const updated = await api.post<SummaryResponse, DecisionRequest>(
        `/api/summary/${summaryId}/decision`,
        { decision },
      )
      // decision 端点已返回更新后的卡片 → 就地替换这一张(权威值覆盖乐观值),
      // 不再整房间重拉(省掉点击后那次 ~4s 的 GET /summary/me + 整页"加载中"闪烁)
      setSummaries(prev => prev.map(s => (s.id === summaryId ? updated : s)))

      // 如果是开聊,试着创建 session 然后跳过去
      if (decision === "open_human_chat") {
        try {
          const session = await api.post<ChatSessionResponse>(`/api/chat/sessions/from-summary/${summaryId}`)
          router.push(`/chat/${session.id}/briefing`)
          return
        } catch (e: any) {
          // 对方还没决定 → 显示一个柔和的 toast,不打断流程
          setNotice("已记下你想开聊。等对方也决定开聊后,真人聊天入口会出现在这里。")
        }
      }
      if (decision === "drop") setNotice("已丢。这个人以后不会再被推给你。")
      if (decision === "re_dispatch") {
        setNotice("收到 — 我去换个话题再跟 TA 聊一场,大概一分钟回来跟你交底。")
        // 后台 BackgroundTask 还在跑,稍后静默刷新拿新简报(不弹整页 loading)
        setTimeout(() => { void loadAll({ silent: true }) }, 30_000)
        setTimeout(() => { void loadAll({ silent: true }) }, 75_000)
      }
    } catch (e: any) {
      setSummaries(snapshot)  // 乐观更新回滚
      setNotice(`决策失败:${e?.detail || e?.message}`)
    } finally {
      setActionPending(null)
    }
  }

  // Tier 1 行为:跟 Agent 聊聊这场简报 — 跟 decision 完全解耦,不写 SummaryDecision
  async function openAgentChat(summaryId: number) {
    setActionPending(summaryId)
    try {
      const resp = await api.post<SummaryResponse>(
        `/api/summary/${summaryId}/agent-chat`,
      )
      const convId = resp?.agent_conversation_id
      if (convId) {
        router.push(`/me/agent/${convId}`)
      } else {
        setNotice("Agent 暂时没空,稍后再试。")
      }
    } catch (e: any) {
      setNotice(`打开失败:${e?.detail || e?.message}`)
    } finally {
      setActionPending(null)
    }
  }

  // 找到 active sessions(用户可以进入的真人聊天)
  const activeSessions = sessions.filter(s => s.status === "active")

  // 双向索引:summary ↔ session
  const summaryById: Record<number, SummaryResponse> = {}
  summaries.forEach(s => { summaryById[s.id] = s })
  const sessionBySourceSummary: Record<number, ChatSessionResponse> = {}
  activeSessions.forEach(s => {
    if (s.source_summary_id != null) sessionBySourceSummary[s.source_summary_id] = s
  })

  function jumpToBriefing(summaryId: number) {
    setExpandedId(summaryId)
    // 下一帧再 scroll(等 setExpandedId 引起的 expand 渲染完)
    requestAnimationFrame(() => {
      const el = document.getElementById(`briefing-${summaryId}`)
      if (!el) return
      el.scrollIntoView({ behavior: "smooth", block: "center" })
      el.classList.add("ring-2", "ring-primary", "ring-offset-2", "ring-offset-bg")
      setTimeout(() => {
        el.classList.remove("ring-2", "ring-primary", "ring-offset-2", "ring-offset-bg")
      }, 1800)
    })
  }

  return (
    <div className="min-h-screen">
      <Topbar active="room" />

      {/* Toast notice */}
      {notice && (
        <div className="fixed top-20 left-1/2 -translate-x-1/2 z-50 bg-ink text-bg px-4 py-3 rounded-md text-sm shadow-modal animate-fade-in max-w-[640px]">
          {notice}
        </div>
      )}

      <main className="max-w-[720px] mx-auto px-6 py-8 pb-24">
        {/* 状态栏 */}
        <div className="bg-bg-elevated border border-line-soft rounded-md px-5 py-4 mb-6 flex items-center gap-3.5">
          <div className="relative flex-shrink-0">
            <span className="block w-2.5 h-2.5 rounded-full bg-primary" />
            <span className="absolute inset-[-4px] rounded-full border-2 border-primary opacity-40 animate-agent-pulse" />
          </div>
          <div className="text-sm text-ink-secondary flex-1">
            {status ? (
              <>
                <div>
                  <span className="text-ink font-medium">Agent 正在聊 {status.chatting_count} 个</span>
                  <span> · 其中 {status.spark_count} 个有戏 · 待决策 {status.total_summaries_pending}</span>
                </div>
                {status.top_hint?.nickname && (
                  <div className="text-xs text-ink-tertiary mt-1 line-clamp-1">
                    其中 <strong className="text-ink-secondary font-medium">@{status.top_hint.nickname}</strong>
                    {status.top_hint.topic && (
                      <> — {status.top_hint.topic}</>
                    )}
                  </div>
                )}
              </>
            ) : "加载中…"}
          </div>
        </div>

        {/* === Active 真人聊天入口卡(双方都决定开聊后) === */}
        {activeSessions.length > 0 && (
          <div className="mb-6 space-y-2.5">
            <div className="text-xs text-ink-secondary tracking-[0.04em] px-1">
              真人聊天进行中
            </div>
            {activeSessions.map(s => {
              const otherUid = s.user_a_id === myUid ? s.user_b_id : s.user_a_id
              const otherNick = s.user_a_id === myUid ? s.user_b_nickname : s.user_a_nickname
              const displayName = otherNick || `user_${otherUid}`
              const avatarChar = (otherNick || `U${otherUid}`).charAt(0)
              const sourceSum = s.source_summary_id != null ? summaryById[s.source_summary_id] : null
              return (
                <Link
                  key={s.id}
                  href={`/chat/${s.id}`}
                  className="block bg-primary-soft border-[1.5px] border-primary rounded-md px-5 py-4 hover:bg-primary-soft/70 transition cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                        {avatarChar}
                      </div>
                      <div>
                        <div className="font-semibold text-primary-dark">和 @{displayName} 的真人聊天</div>
                        <div className="text-xs text-ink-secondary mt-0.5">
                          {s.last_message_at
                            ? `最近一条 ${new Date(s.last_message_at).toLocaleString("zh-CN")}`
                            : "等你开口"}
                        </div>
                        {sourceSum && (
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              jumpToBriefing(sourceSum.id)
                            }}
                            className="text-[11px] text-ink-tertiary hover:text-primary-dark mt-1 transition"
                          >
                            源自《{sourceSum.verdict}》{new Date(sourceSum.created_at).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })} 那张 ↑
                          </button>
                        )}
                      </div>
                    </div>
                    <span className="text-primary-dark font-medium text-sm">进入 →</span>
                  </div>
                </Link>
              )
            })}
          </div>
        )}

        {/* === 简报卡列表 === */}
        <div className="space-y-3">
          {loading && <p className="text-center py-12 text-ink-secondary">加载中…</p>}

          {!loading && summaries.length === 0 && activeSessions.length === 0 && (
            <div className="bg-bg-elevated border border-dashed border-line rounded-lg px-8 py-16 text-center">
              <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-primary-soft border-[1.5px] border-dashed border-primary flex items-center justify-center">
                <span className="w-3.5 h-3.5 rounded-full bg-primary" />
              </div>
              <h3 className="text-lg font-semibold mb-2">还没有简报</h3>
              <p className="text-sm text-ink-secondary leading-relaxed mb-6 max-w-sm mx-auto">
                你的 Agent 正在认识平台上的其他人。
              </p>
              <p className="text-xs text-ink-tertiary">
                Agent 互聊有 LLM 调用延迟,等几分钟再回来看。
              </p>
            </div>
          )}

          {summaries.map(s => {
            const expanded = expandedId === s.id
            const decided = !!s.user_decision
            const isPreBriefing = s.summary_type === "pre_briefing"
            const isObservation = s.summary_type === "human_chat_observation"
            const canViewAgentChat = !!s.agent_chat_id  // 只有源自 agent_chat 的简报能查看互聊
            const linkedSession = sessionBySourceSummary[s.id]  // 该简报衍生出的活跃 session(若有)

            return (
              <article
                key={s.id}
                id={`briefing-${s.id}`}
                className={`bg-bg-elevated border rounded-md p-5 transition cursor-pointer ${
                  decided ? "border-line-soft opacity-70" : expanded ? "border-line shadow-md" : "border-line-soft hover:border-line shadow-card"
                }`}
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("button")) return
                  if ((e.target as HTMLElement).closest("a")) return
                  if (decided && !expanded) return
                  setExpandedId(expanded ? null : s.id)
                }}
              >
                {/* === IA 第一梯队:对方 nickname + 当前状态(verdict)+ 头像 === */}
                <div className="flex items-start gap-3.5">
                  {(s.peer_nickname || s.peer_user_id) ? (
                    <div className="w-11 h-11 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary text-white text-sm font-semibold flex items-center justify-center flex-shrink-0">
                      {(s.peer_nickname || `U${s.peer_user_id}`).charAt(0)}
                    </div>
                  ) : (
                    <div className="w-11 h-11 rounded-full bg-bg-soft text-ink-tertiary text-sm flex items-center justify-center flex-shrink-0">
                      ?
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="text-[16px] font-semibold truncate">
                        {(s.peer_nickname || s.peer_user_id)
                          ? `@${s.peer_nickname || `user_${s.peer_user_id}`}`
                          : "（未知对方）"}
                      </h3>
                      <span className={`text-[13px] font-semibold tracking-tight px-2 py-0.5 rounded-md ${
                        s.verdict === "来电" ? "bg-primary-soft text-primary-dark"
                        : s.verdict === "不合" ? "bg-bg-soft text-ink-tertiary"
                        : "bg-[rgba(255,215,0,0.18)] text-[#9a7800]"
                      }`}>
                        {s.verdict}
                      </span>
                      {isPreBriefing && <span className="text-[10px] bg-primary-soft text-primary-dark rounded-full px-2 py-0.5">真人聊前简报</span>}
                      {isObservation && <span className="text-[10px] bg-[rgba(255,215,0,0.18)] text-[#B8860B] rounded-full px-2 py-0.5">观察报告</span>}
                    </div>
                    <div className="text-[11px] text-ink-tertiary mt-0.5">
                      你的 Agent · {new Date(s.created_at).toLocaleString("zh-CN")}
                    </div>
                  </div>
                </div>

                {!expanded && s.highlights[0] && (
                  <div className="mt-3 text-[14.5px] leading-relaxed text-ink">
                    {s.highlights[0].text}
                  </div>
                )}

                {decided && !expanded && (
                  <div className="mt-3 text-xs text-ink-tertiary flex items-center gap-2 flex-wrap">
                    <span>已决策:{decisionLabel(s.user_decision!)}</span>
                    {s.user_decision === "open_human_chat" && !linkedSession && (
                      <span>· 等对方也决定中…</span>
                    )}
                    {s.user_decision === "open_human_chat" && linkedSession && (
                      <Link
                        href={`/chat/${linkedSession.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-primary-dark hover:underline font-medium"
                      >
                        · 进入这场聊天 →
                      </Link>
                    )}
                    {s.user_decision === "re_dispatch" && (
                      <span>· Agent 在换话题再聊,稍后会有新简报</span>
                    )}
                  </div>
                )}

                {expanded && (
                  <div className="mt-4 pt-4 border-t border-line-soft space-y-4">
                    {s.highlights.length > 0 && (
                      <div>
                        <div className="text-xs text-ink-secondary tracking-[0.02em] mb-2">值得关注</div>
                        {s.highlights.map((h, i) => (
                          <div key={i} className="text-[14.5px] leading-relaxed mb-2 pl-3 border-l-2 border-primary-soft">
                            {h.text}
                          </div>
                        ))}
                      </div>
                    )}
                    {s.risks.length > 0 && (
                      <div>
                        <div className="text-xs text-ink-secondary tracking-[0.02em] mb-2">需要留意</div>
                        {s.risks.map((r, i) => (
                          <div key={i} className="text-[14.5px] leading-relaxed mb-2 pl-3 border-l-2 border-warn-soft">
                            {r.text}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* === Tier 1:和 Agent 一起想想 ─ 持续性,随时可以来 === */}
                    <div className="pt-2">
                      <div className="text-[11px] text-ink-tertiary tracking-[0.04em] mb-2">
                        和 Agent 一起想想
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); void openAgentChat(s.id) }}
                          disabled={actionPending === s.id}
                          className="text-xs text-ink hover:text-primary-dark border-[1.5px] border-line-soft hover:border-primary rounded-full px-3.5 py-1.5 transition flex items-center gap-1.5 disabled:opacity-50"
                        >
                          <span>💬</span>
                          <span>
                            {s.agent_conversation_id ? "继续跟我 Agent 聊" : "跟我 Agent 聊聊这场"}
                          </span>
                        </button>
                        {canViewAgentChat && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setViewerSummaryId(s.id) }}
                            className="text-xs text-ink-secondary hover:text-primary-dark border-[1.5px] border-line-soft hover:border-primary rounded-full px-3.5 py-1.5 transition flex items-center gap-1.5"
                          >
                            <span>👀</span>
                            <span>看看 Agent 们都聊了什么</span>
                          </button>
                        )}
                      </div>
                    </div>

                    {/* === Tier 2:决定 ─ 一次性终局动作,选了 一个就锁住 === */}
                    {!decided ? (
                      <div className="pt-3 border-t border-dashed border-line-soft">
                        <div className="text-[11px] text-ink-tertiary tracking-[0.04em] mb-2">
                          决定
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <ActionBtn
                            label="开真人聊天"
                            primary={s.recommended_action === "开真人聊天"}
                            loading={actionPending === s.id}
                            onClick={() => decide(s.id, "open_human_chat")}
                          />
                          <ActionBtn
                            label="再派一次"
                            primary={s.recommended_action === "再派一次"}
                            loading={actionPending === s.id}
                            onClick={() => decide(s.id, "re_dispatch")}
                          />
                          <ActionBtn
                            label="丢"
                            warn
                            loading={actionPending === s.id}
                            onClick={() => decide(s.id, "drop")}
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-ink-tertiary pt-2 border-t border-dashed border-line-soft flex items-center gap-2 flex-wrap">
                        <span>已决策:<strong className="text-ink">{decisionLabel(s.user_decision!)}</strong></span>
                        {s.decided_at && <span>· {new Date(s.decided_at).toLocaleString("zh-CN")}</span>}
                        {s.user_decision === "open_human_chat" && linkedSession && (
                          <Link
                            href={`/chat/${linkedSession.id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="ml-auto text-primary-dark hover:underline font-medium"
                          >
                            进入这场聊天 →
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </article>
            )
          })}
        </div>
      </main>

      {/* Agent 互聊 viewer modal */}
      {viewerSummaryId && (
        <AgentChatViewer
          summaryId={viewerSummaryId}
          open={true}
          onClose={() => setViewerSummaryId(null)}
        />
      )}
    </div>
  )
}

function decisionLabel(d: string): string {
  const map: Record<string, string> = {
    open_human_chat: "开真人聊天",
    re_dispatch: "再派一次",
    drop: "丢",
    // chat_with_my_agent 是历史值(从 decision 退役),只在迁移前的老数据上出现;
    // 迁移会删掉这些行,但留个 label 兜底
    chat_with_my_agent: "跟我 Agent 聊聊",
  }
  return map[d] || d
}

function ActionBtn(p: { label: string; primary?: boolean; warn?: boolean; loading?: boolean; onClick: () => void }) {
  return (
    <button
      disabled={p.loading}
      onClick={p.onClick}
      className={`px-4 py-2 rounded-md text-sm font-medium border-[1.5px] transition disabled:opacity-50 ${
        p.warn
          ? "border-warn-soft text-warn hover:bg-warn-soft"
          : p.primary
          ? "border-primary text-primary hover:bg-primary-soft"
          : "border-line text-ink hover:border-ink-secondary"
      }`}
    >
      {p.label}
    </button>
  )
}
