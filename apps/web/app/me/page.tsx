"use client"

/**
 * "我" tab · 用户身份级事项
 *
 * 按 cybermomo/交互拆解/_信息架构.md §5:
 *   - 我的 .md(可看,改走 Agent 对话 — Phase 4 之后)
 *   - 我的资料(可改 → 跳 /md/basic)
 *   - 拉黑名单(软拉黑可解除)
 *   - 通知设置(MVP 不实装)
 *   - 设置 / 帐号(退出 / 注销)
 *   - 重读 Onboarding
 */
import Link from "next/link"
import { useEffect, useState } from "react"

import AvatarUpload from "@/components/AvatarUpload"
import MbtiPicker from "@/components/MbtiPicker"
import Toast from "@/components/Toast"
import Topbar from "@/components/Topbar"
import {
  api,
  type MdDocumentResponse,
  type UpsertProfileRequest,
  type UserMeResponse,
} from "@/lib/api"

const AGE_OPTIONS = ["18-25", "25-30", "30-35", "35-40", "40+"] as const
const GENDER_OPTIONS = [
  { val: "female", label: "女" },
  { val: "male", label: "男" },
  { val: "non_binary", label: "非二元" },
  { val: "prefer_not_to_say", label: "不愿透露" },
] as const

const GENDER_LABEL: Record<string, string> = {
  female: "女",
  male: "男",
  non_binary: "非二元",
  prefer_not_to_say: "不愿透露",
}

interface SoftBlockEntry {
  blocked_user_id: number
  blocked_nickname?: string | null
  reason?: string | null
  created_at: string
}

interface AgentChatHistoryItem {
  agent_chat_id: number
  match_id: number
  peer_user_id: number
  peer_nickname?: string | null
  status: string
  end_reason?: string | null
  turns: number
  started_at?: string | null
  related_summary_id?: number | null
  related_verdict?: string | null
  user_decision?: string | null
}

export default function MePage() {
  const [me, setMe] = useState<UserMeResponse | null>(null)
  const [md, setMd] = useState<MdDocumentResponse | null>(null)
  const [blocklist, setBlocklist] = useState<SoftBlockEntry[]>([])
  const [agentChats, setAgentChats] = useState<AgentChatHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)
  // 软拉黑解除二次确认:点过一次的 uid 在这里,再点一下才真执行
  const [armedUnblockUid, setArmedUnblockUid] = useState<number | null>(null)

  useEffect(() => { void load() }, [])

  async function load() {
    setLoading(true)
    try {
      const [meRes, mdRes, bl, ac] = await Promise.all([
        api.get<UserMeResponse>("/api/auth/me").catch(() => null),
        api.get<MdDocumentResponse>("/api/md/me").catch(() => null),
        api.get<SoftBlockEntry[]>("/api/room/blocklist").catch(() => []),
        api.get<AgentChatHistoryItem[]>("/api/agent_chat/me").catch(() => []),
      ])
      setMe(meRes)
      setMd(mdRes)
      setBlocklist(bl || [])
      setAgentChats(ac || [])
    } finally { setLoading(false) }
  }

  async function unblock(uid: number) {
    // 点第一次:armed,文案变 → 给用户 5s 反悔窗口
    if (armedUnblockUid !== uid) {
      setArmedUnblockUid(uid)
      setTimeout(() => {
        setArmedUnblockUid(prev => (prev === uid ? null : prev))
      }, 5000)
      return
    }
    // 点第二次:真执行
    setArmedUnblockUid(null)
    const target = blocklist.find(b => b.blocked_user_id === uid)
    try {
      await api.del(`/api/room/blocklist/${uid}`)
      setNotice(`已解除对 ${softBlockName(target)} 的软拉黑。`)
      await load()
    } catch (e: any) {
      setNotice(`解除失败:${e?.detail || e?.message}`)
    }
  }

  // 退出登录 — armed pattern,跟解除软拉黑一致
  const [armedLogout, setArmedLogout] = useState(false)

  async function logout() {
    if (!armedLogout) {
      setArmedLogout(true)
      setTimeout(() => setArmedLogout(false), 5000)
      return
    }
    setArmedLogout(false)
    try {
      await api.post("/api/auth/logout")
    } catch {
      // 即使 200 失败也清前端状态;cookie 客户端无法手动清,刷到 / 让 fetch /api/auth/me 触发 401 再跳
    } finally {
      // 跳登录页(浏览器会发现 cookie 没了,自然回到未登录状态)
      window.location.href = "/"
    }
  }

  return (
    <div className="min-h-screen">
      <Topbar active="me" />

      <Toast message={notice} onClose={() => setNotice(null)} />

      <main className="max-w-[640px] mx-auto px-6 py-8 pb-24">
        {loading && <p className="text-center py-12 text-ink-secondary">加载中…</p>}

        {!loading && (
          <>
            {/* 头像 + 昵称 */}
            <section className="flex items-center gap-4 mb-8">
              <div className="w-16 h-16 rounded-full overflow-hidden bg-gradient-to-br from-[#C7E8D5] to-primary flex items-center justify-center text-white text-[22px] font-semibold flex-shrink-0">
                {me?.profile?.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={me.profile.avatar_url} alt="avatar" className="w-full h-full object-cover" />
                ) : (
                  me?.profile?.nickname?.charAt(0) || "?"
                )}
              </div>
              <div>
                <div className="text-xl font-semibold">{me?.profile?.nickname || "未设置昵称"}</div>
                <div className="text-sm text-ink-secondary">
                  {me?.profile?.age_band || "—"} · {genderDisplay(me?.profile?.gender) || "—"} · {me?.profile?.mbti || "—"}
                </div>
                <div className="text-xs text-ink-tertiary mt-1">
                  {me?.email || "账号资料未同步"}
                </div>
              </div>
            </section>

            {/* 我的 .md */}
            <Section title="我的 .md">
              {md ? (
                <Card>
                  <div className="text-base font-semibold text-primary-dark mb-2">{md.portrait_title}</div>
                  <div className="text-xs text-ink-tertiary mb-3">
                    生成于 {new Date(md.created_at).toLocaleString("zh-CN")}
                  </div>
                  {md.portrait_body[0] && (
                    <p className="text-sm text-ink-secondary leading-relaxed">{md.portrait_body[0]}</p>
                  )}
                  <div className="mt-4 text-xs text-ink-tertiary leading-relaxed">
                    这份 .md 对你本人可见,也会交给你的 Agent 使用;其他用户看不到原文。
                    要改方向,可以通过<strong className="text-ink">「跟自己 Agent 对话」</strong>慢慢说。
                    现在可以重做问卷整体覆盖。
                  </div>
                  <div className="mt-4 flex gap-2">
                    <Link href="/md/quiz" className="text-sm text-primary border-[1.5px] border-primary px-4 py-2 rounded-full hover:bg-primary-soft transition font-medium">
                      重做 17 题
                    </Link>
                  </div>
                </Card>
              ) : (
                <Card>
                  <p className="text-ink-secondary">还没生成 .md。</p>
                  <Link href="/md/quiz" className="inline-block mt-3 text-sm text-primary font-medium">
                    去做问卷 →
                  </Link>
                </Card>
              )}
            </Section>

            {/* 我的资料 */}
            <Section title="我的资料">
              <ProfileCard
                me={me}
                onSaved={(updated) => {
                  setMe(updated)
                  setNotice("资料已保存。")
                }}
                onError={(msg) => setNotice(msg)}
              />
            </Section>

            {/* Agent 替我聊过的所有场次 */}
            <Section title={`Agent 替我聊过谁(${agentChats.length})`}>
              {agentChats.length === 0 ? (
                <Card>
                  <p className="text-ink-secondary text-sm">还没有 Agent 互聊记录。</p>
                  <p className="text-xs text-ink-tertiary mt-2 leading-relaxed">
                    生成 .md 之后,Agent 会去认识平台上的其他人 — 那些会在这里。
                  </p>
                </Card>
              ) : (
                <Card>
                  <p className="text-xs text-ink-tertiary leading-relaxed mb-4">
                    我替你聊过的所有人都在这。点开看那场聊了什么 — 你想看的时候才看,选择权在你。
                  </p>
                  <div className="space-y-2">
                    {agentChats.slice(0, 5).map(c => (
                      <Link
                        key={c.agent_chat_id}
                        href={c.related_summary_id ? `/me/agent-chats?focus=${c.related_summary_id}` : `/me/agent-chats`}
                        className="block bg-bg border border-line-soft hover:border-line rounded-md px-4 py-3 transition"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 text-sm">
                              <span className="font-medium">{c.peer_nickname ? `@${c.peer_nickname}` : "这位用户"}</span>
                              {c.related_verdict && (
                                <span className={`text-xs px-2 py-0.5 rounded-full ${verdictBadgeClass(c.related_verdict)}`}>
                                  {c.related_verdict}
                                </span>
                              )}
                              {c.status === "re_dispatched" && (
                                <span className="text-[10px] text-ink-tertiary border border-line-soft rounded-full px-1.5 py-0.5">已换话题再派</span>
                              )}
                              {c.status === "running" && (
                                <span className="text-[10px] text-primary-dark border border-primary-soft rounded-full px-1.5 py-0.5">聊着</span>
                              )}
                            </div>
                            <div className="text-xs text-ink-tertiary mt-1">
                              {c.turns} 轮 · {c.started_at ? new Date(c.started_at).toLocaleString("zh-CN") : ""}
                              {c.user_decision && <> · 已决策:{decisionLabelMe(c.user_decision)}</>}
                            </div>
                          </div>
                          <span className="text-xs text-ink-tertiary flex-shrink-0">查看 →</span>
                        </div>
                      </Link>
                    ))}
                  </div>
                  {agentChats.length > 5 && (
                    <Link
                      href="/me/agent-chats"
                      className="mt-4 inline-block text-sm text-primary border-[1.5px] border-primary px-4 py-2 rounded-full hover:bg-primary-soft transition font-medium"
                    >
                      看全部 {agentChats.length} 场 →
                    </Link>
                  )}
                </Card>
              )}
            </Section>

            {/* 拉黑名单 */}
            <Section title={`软拉黑(${blocklist.length})`}>
              {blocklist.length === 0 ? (
                <Card><p className="text-ink-secondary text-sm">还没拉黑任何人。</p></Card>
              ) : (
                <Card>
                  <div className="space-y-3">
                    {blocklist.map(b => (
                      <div key={b.blocked_user_id} className="flex items-center justify-between gap-3 py-2 border-b border-line-soft last:border-b-0">
                        <div>
                          <div className="text-sm font-medium">{softBlockName(b)}</div>
                          <div className="text-xs text-ink-tertiary">
                            {softBlockReasonLabel(b.reason)} · {new Date(b.created_at).toLocaleString("zh-CN")}
                          </div>
                        </div>
                        <button
                          onClick={() => unblock(b.blocked_user_id)}
                          className={`text-xs px-3 py-1.5 border rounded-md transition ${
                            armedUnblockUid === b.blocked_user_id
                              ? "border-warn text-warn bg-warn-soft font-medium"
                              : "border-line-soft text-ink-secondary hover:border-warn hover:text-warn"
                          }`}
                        >
                          {armedUnblockUid === b.blocked_user_id ? "确定解除?" : "解除"}
                        </button>
                      </div>
                    ))}
                  </div>
                </Card>
              )}
              <p className="text-xs text-ink-tertiary mt-2 leading-relaxed">
                软拉黑只影响以后的匹配推荐 — 不会通知对方。
                平台底线拉黑(违规留底)是另一回事,你看不到也解不了。
              </p>
            </Section>

            {/* 设置 */}
            <Section title="设置 / 帐号">
              <Card>
                <div className="space-y-2 text-sm">
                  <Link
                    href="/me/agent"
                    className="flex items-center justify-between gap-3 py-2 -mx-1 px-1 rounded hover:bg-bg-soft transition group"
                  >
                    <span>跟我的 Agent 聊过什么</span>
                    <span className="text-xs text-ink-tertiary group-hover:text-ink-secondary">看 →</span>
                  </Link>
                  <Link
                    href="/changelog"
                    className="flex items-center justify-between gap-3 py-2 -mx-1 px-1 rounded hover:bg-bg-soft transition group"
                  >
                    <span>更新日志</span>
                    <span className="text-xs text-ink-tertiary group-hover:text-ink-secondary">看 →</span>
                  </Link>
                  <Link
                    href="/onboarding"
                    className="flex items-center justify-between gap-3 py-2 -mx-1 px-1 rounded hover:bg-bg-soft transition group"
                  >
                    <span>重读 Onboarding</span>
                    <span className="text-xs text-ink-tertiary group-hover:text-ink-secondary">看 →</span>
                  </Link>
                  <button
                    type="button"
                    onClick={logout}
                    className={`w-full flex items-center justify-between gap-3 py-2 -mx-1 px-1 rounded transition text-left ${
                      armedLogout ? "bg-warn-soft text-warn" : "hover:bg-bg-soft"
                    }`}
                  >
                    <span>{armedLogout ? "确定退出?" : "退出登录"}</span>
                    <span className={`text-xs ${armedLogout ? "text-warn" : "text-ink-tertiary"}`}>
                      {armedLogout ? "再点一次" : "点 →"}
                    </span>
                  </button>
                  <DisabledRow label="通知设置" hint="MVP 阶段不主动推,后续接入" />
                  <DisabledRow label="注销账户" hint="发邮件到 hi@cybermomo.com 人工处理" />
                </div>
              </Card>
            </Section>
          </>
        )}
      </main>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-xs text-ink-secondary tracking-[0.04em] mb-3 px-1">{title}</h2>
      {children}
    </section>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-elevated border border-line-soft rounded-md p-5 shadow-card">
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <span className="text-ink-secondary text-xs flex-shrink-0">{label}</span>
      <span className="text-ink">{value}</span>
    </div>
  )
}

function DisabledRow({ label, hint }: { label: string; hint: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 opacity-50">
      <span>{label}</span>
      <span className="text-xs text-ink-tertiary">{hint}</span>
    </div>
  )
}

function verdictBadgeClass(v: string): string {
  if (v === "来电") return "bg-primary-soft text-primary-dark"
  if (v === "不合") return "bg-bg border border-line-soft text-ink-tertiary"
  return "bg-[rgba(255,215,0,0.15)] text-[#9a7800]"
}

function decisionLabelMe(d: string): string {
  const map: Record<string, string> = {
    open_human_chat: "开聊",
    re_dispatch: "再派",
    drop: "丢",
    chat_with_my_agent: "调方向",
  }
  return map[d] || d
}

function softBlockName(entry?: SoftBlockEntry | null): string {
  const nickname = entry?.blocked_nickname?.trim()
  return nickname ? `@${nickname}` : "这位用户"
}

function softBlockReasonLabel(reason?: string | null): string {
  const map: Record<string, string> = {
    "dropped from summary card": "你在简报卡里点了「丢」",
    "blocked from chat session": "你在真人聊天里拉黑了 TA",
    reported: "你举报后自动加入软拉黑",
  }
  return map[reason || ""] || "你主动加入软拉黑"
}

function genderDisplay(gender?: string | null): string | null {
  return gender ? GENDER_LABEL[gender] || null : null
}

// 我的资料卡 — 视图 / 编辑两态切换,不跳回问卷流程
function ProfileCard({
  me,
  onSaved,
  onError,
}: {
  me: UserMeResponse | null
  onSaved: (updated: UserMeResponse) => void
  onError: (msg: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [nickname, setNickname] = useState("")
  const [ageBand, setAgeBand] = useState<string>("")
  const [gender, setGender] = useState<string>("")
  const [mbti, setMbti] = useState<string | null>(null)
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  function startEdit() {
    setNickname(me?.profile?.nickname || "")
    setAgeBand(me?.profile?.age_band || AGE_OPTIONS[1])
    setGender(me?.profile?.gender || "prefer_not_to_say")
    setMbti(me?.profile?.mbti || null)
    setAvatarUrl(me?.profile?.avatar_url || null)
    setEditing(true)
  }

  async function save() {
    if (!nickname.trim()) {
      onError("昵称不能为空")
      return
    }
    setSaving(true)
    try {
      const body: UpsertProfileRequest = {
        profile: {
          nickname: nickname.trim(),
          age_band: ageBand,
          gender,
          mbti: mbti || undefined,
          avatar_url: avatarUrl || undefined,
        },
      }
      const updated = await api.put<UserMeResponse, UpsertProfileRequest>(
        "/api/auth/me/profile", body,
      )
      onSaved(updated)
      setEditing(false)
    } catch (e: any) {
      onError(e?.detail || e?.message || "保存失败")
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <Card>
        <div className="text-sm space-y-2 text-ink">
          <Row label="昵称" value={me?.profile?.nickname || "未设置"} />
          <Row label="年龄段" value={me?.profile?.age_band || "未设置"} />
          <Row label="性别" value={GENDER_LABEL[me?.profile?.gender || ""] || "未设置"} />
          <Row label="MBTI" value={me?.profile?.mbti || "未设置"} />
        </div>
        <button
          onClick={startEdit}
          className="mt-4 inline-block text-sm text-primary border-[1.5px] border-primary px-4 py-2 rounded-full hover:bg-primary-soft transition font-medium"
        >
          修改资料
        </button>
      </Card>
    )
  }

  return (
    <Card>
      <div className="space-y-4">
        <div>
          <div className="text-[12px] text-ink-secondary mb-1.5">头像</div>
          <AvatarUpload
            value={avatarUrl}
            onChange={setAvatarUrl}
            fallbackInitial={nickname}
            googleAvatarUrl={me?.google_avatar_url || undefined}
          />
        </div>

        <div>
          <div className="text-[12px] text-ink-secondary mb-1.5">昵称</div>
          <input
            value={nickname}
            onChange={e => setNickname(e.target.value)}
            maxLength={20}
            className="w-full px-3 py-2 border-[1.5px] border-line-soft rounded-md text-sm focus:outline-none focus:border-primary bg-bg-elevated"
          />
        </div>

        <div>
          <div className="text-[12px] text-ink-secondary mb-1.5">年龄段</div>
          <ChipsRow
            options={AGE_OPTIONS.map(a => ({ val: a, label: a }))}
            value={ageBand}
            onChange={setAgeBand}
          />
        </div>

        <div>
          <div className="text-[12px] text-ink-secondary mb-1.5">性别</div>
          <ChipsRow
            options={GENDER_OPTIONS as any}
            value={gender}
            onChange={setGender}
          />
        </div>

        <div>
          <div className="text-[12px] text-ink-secondary mb-1.5">MBTI</div>
          <MbtiPicker value={mbti} onChange={setMbti} />
        </div>

        <div className="flex items-center gap-2 pt-2 border-t border-line-soft">
          <button
            onClick={save}
            disabled={saving || !nickname.trim()}
            className="bg-primary text-white px-5 py-2 rounded-full text-sm font-medium hover:bg-primary-dark transition disabled:opacity-40"
          >
            {saving ? "保存中…" : "保存"}
          </button>
          <button
            onClick={() => setEditing(false)}
            disabled={saving}
            className="text-sm text-ink-secondary hover:text-ink px-3 py-2 transition"
          >
            取消
          </button>
        </div>
      </div>
    </Card>
  )
}

function ChipsRow<T extends string>(p: {
  options: { val: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {p.options.map(o => (
        <button
          key={o.val}
          onClick={() => p.onChange(o.val)}
          className={`px-3.5 py-1.5 rounded-full border-[1.5px] text-[13px] transition ${
            o.val === p.value
              ? "bg-primary-soft border-primary text-primary-dark font-medium"
              : "bg-bg-elevated border-line-soft text-ink hover:border-ink-secondary"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
