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

  const myUid = Number(getMockUserId())

  useEffect(() => { void loadAll() }, [])
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 5000)
    return () => clearTimeout(t)
  }, [notice])

  async function loadAll() {
    setLoading(true)
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
    try {
      await api.post<SummaryResponse, DecisionRequest>(
        `/api/summary/${summaryId}/decision`,
        { decision },
      )
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
      if (decision === "re_dispatch") setNotice("已请求再派一次(MVP 阶段先记着,后续会真的换话题再跑一场)。")
      if (decision === "chat_with_my_agent") setNotice("'跟我 Agent 聊聊' 入口稍后接(对应右下悬浮 — 全局 Agent 对话)。")
      await loadAll()
    } catch (e: any) {
      setNotice(`决策失败:${e?.detail || e?.message}`)
    } finally {
      setActionPending(null)
    }
  }

  // 找到 active sessions(用户可以进入的真人聊天)
  const activeSessions = sessions.filter(s => s.status === "active")

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
          <div className="text-sm text-ink-secondary">
            {status ? (
              <>
                <span className="text-ink font-medium">Agent 正在聊 {status.chatting_count} 个</span>
                <span> · 其中 {status.spark_count} 个有戏 · 待决策 {status.total_summaries_pending}</span>
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
              return (
                <Link
                  key={s.id}
                  href={`/chat/${s.id}`}
                  className="block bg-primary-soft border-[1.5px] border-primary rounded-md px-5 py-4 hover:bg-primary-soft/70 transition cursor-pointer"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#C7E8D5] to-primary flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
                        U{otherUid}
                      </div>
                      <div>
                        <div className="font-semibold text-primary-dark">和 @user_{otherUid} 的真人聊天</div>
                        <div className="text-xs text-ink-secondary mt-0.5">
                          {s.last_message_at
                            ? `最近一条 ${new Date(s.last_message_at).toLocaleString("zh-CN")}`
                            : "等你开口"}
                        </div>
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

            return (
              <article
                key={s.id}
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
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-primary" />
                    <span className="text-xs text-ink-secondary">
                      你的 Agent
                      {isPreBriefing && <span className="ml-2 text-[10px] bg-primary-soft text-primary-dark rounded-full px-2 py-0.5">真人聊前简报</span>}
                      {isObservation && <span className="ml-2 text-[10px] bg-[rgba(255,215,0,0.18)] text-[#B8860B] rounded-full px-2 py-0.5">观察报告</span>}
                    </span>
                  </div>
                  <div className="text-xs text-ink-tertiary">{new Date(s.created_at).toLocaleString("zh-CN")}</div>
                </div>

                <div className="flex items-baseline gap-3.5 mt-2">
                  <div className={`text-[22px] font-semibold tracking-tight ${verdictColor(s.verdict)}`}>{s.verdict}</div>
                </div>

                {!expanded && s.highlights[0] && (
                  <div className="mt-3 text-[14.5px] leading-relaxed text-ink">
                    {s.highlights[0].text}
                  </div>
                )}

                {decided && !expanded && (
                  <div className="mt-3 text-xs text-ink-tertiary">
                    已决策:{decisionLabel(s.user_decision!)}
                    {s.user_decision === "open_human_chat" && !activeSessions.some(as => as.match_id) && (
                      <span> · 等对方也决定中…</span>
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

                    {/* 看 Agent 互聊入口(铁律允许:只暴露 utterance + public_signals,对方 private 永不出现)*/}
                    {canViewAgentChat && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setViewerSummaryId(s.id) }}
                        className="text-xs text-ink-secondary hover:text-primary-dark border border-line-soft hover:border-primary rounded-full px-3 py-1.5 transition flex items-center gap-1.5"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                        看看 Agent 们都聊了什么 →
                      </button>
                    )}

                    {/* 决策按钮(只在未决策时显示) */}
                    {!decided && (
                      <div className="flex flex-wrap gap-2 pt-2">
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
                          label="跟我 Agent 聊聊"
                          primary={s.recommended_action === "跟我聊聊调方向"}
                          loading={actionPending === s.id}
                          onClick={() => decide(s.id, "chat_with_my_agent")}
                        />
                        <ActionBtn
                          label="丢"
                          warn
                          loading={actionPending === s.id}
                          onClick={() => decide(s.id, "drop")}
                        />
                      </div>
                    )}

                    {decided && (
                      <div className="text-xs text-ink-tertiary pt-2 border-t border-dashed border-line-soft">
                        已决策:<strong className="text-ink">{decisionLabel(s.user_decision!)}</strong>
                        {s.decided_at && <> · {new Date(s.decided_at).toLocaleString("zh-CN")}</>}
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
