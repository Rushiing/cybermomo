"use client"

/**
 * 广场 · 像素点社交生态
 *
 * 第一版:
 * - GET /api/plaza/feed 拉公开/脱敏字段
 * - 点节点 / 气泡打开社交名片
 * - POST /api/plaza/initiate 真实派出 Agent,结果回个人房间
 */
import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"

import Toast from "@/components/Toast"
import Topbar from "@/components/Topbar"
import {
  api,
  type PlazaFeedResponse,
  type PlazaInitiateRequest,
  type PlazaInitiateResponse,
  type PlazaLink,
  type PlazaNode,
} from "@/lib/api"

const LINK_LABEL: Record<PlazaLink["kind"], string> = {
  shallow_probe: "浅层试探",
  deep_chat: "Agent 互聊",
  human_chat: "真人聊天",
}

type FieldCloudView = {
  label: string
  x: number
  y: number
  width: number
  tone: "mint" | "sky" | "gold" | "slate"
  weight: number
  active: boolean
}

type FieldPullView = {
  user_id: number
  label: string
  x1: number
  y1: number
  x2: number
  y2: number
  active: boolean
  strength: number
}

const FIELD_ANCHORS = [
  { x: 18, y: 25, tone: "mint" as const },
  { x: 45, y: 21, tone: "sky" as const },
  { x: 73, y: 29, tone: "gold" as const },
  { x: 84, y: 55, tone: "slate" as const },
  { x: 63, y: 77, tone: "mint" as const },
  { x: 36, y: 76, tone: "sky" as const },
  { x: 17, y: 55, tone: "gold" as const },
]

const DOMAIN_WEIGHTS = [1, 0.72, 0.5, 0.34]

export default function PlazaPage() {
  const [feed, setFeed] = useState<PlazaFeedResponse | null>(null)
  const [selected, setSelected] = useState<PlazaNode | null>(null)
  const [hoveredId, setHoveredId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [initiatingId, setInitiatingId] = useState<number | null>(null)
  const [handoff, setHandoff] = useState<{
    message: string
    href: string
    label: string
  } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.get<PlazaFeedResponse>("/api/plaza/feed")
      setFeed(resp)
    } catch (e: any) {
      setError(e?.detail || e?.message || "广场暂时进不去")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  async function initiate(target: PlazaNode) {
    if (target.is_self) return
    setInitiatingId(target.user_id)
    setError(null)
    try {
      const resp = await api.post<PlazaInitiateResponse, PlazaInitiateRequest>(
        "/api/plaza/initiate",
        { target_user_id: target.user_id },
      )
      setNotice(resp.message)
      setHandoff({
        message: resp.message,
        href: resp.summary_id ? `/room?focus=${resp.summary_id}` : "/room",
        label: resp.status === "already_done" ? "查看这份简报" : "去个人房间等简报",
      })
      setSelected(null)
      await load()
    } catch (e: any) {
      setNotice(e?.detail || e?.message || "这次没派出去,稍后再试。")
    } finally {
      setInitiatingId(null)
    }
  }

  const plazaFeed = useMemo(() => layoutPlazaFeed(feed), [feed])
  const nodeById = useMemo(() => {
    const out: Record<number, PlazaNode> = {}
    plazaFeed?.nodes.forEach(n => { out[n.user_id] = n })
    return out
  }, [plazaFeed])
  const visibleLinkKinds = useMemo(() => {
    return new Set(plazaFeed?.links.map(link => link.kind) || [])
  }, [plazaFeed])
  const selfUserId = useMemo(
    () => plazaFeed?.nodes.find(n => n.is_self)?.user_id || null,
    [plazaFeed],
  )
  const selectedSelfLinkKind = useMemo(() => {
    if (!plazaFeed || !selected || !selfUserId) return null
    return plazaFeed.links.find(link =>
      (link.source_user_id === selfUserId && link.target_user_id === selected.user_id)
      || (link.target_user_id === selfUserId && link.source_user_id === selected.user_id)
    )?.kind || null
  }, [plazaFeed, selected, selfUserId])
  const activeUserId = selected?.user_id || hoveredId
  const activeRelatedIds = useMemo(() => {
    const out = new Set<number>()
    if (!plazaFeed || !activeUserId) return out
    plazaFeed.links.forEach(link => {
      if (link.source_user_id === activeUserId) out.add(link.target_user_id)
      if (link.target_user_id === activeUserId) out.add(link.source_user_id)
    })
    return out
  }, [plazaFeed, activeUserId])
  const fieldClouds = useMemo(
    () => makeFieldClouds(plazaFeed?.nodes || [], activeUserId ? nodeById[activeUserId] || null : null),
    [activeUserId, nodeById, plazaFeed],
  )
  const fieldPulls = useMemo(
    () => makeFieldPulls(
      plazaFeed?.nodes || [],
      fieldClouds,
      activeUserId,
      activeRelatedIds,
      selfUserId,
    ),
    [activeRelatedIds, activeUserId, fieldClouds, plazaFeed, selfUserId],
  )

  return (
    <div className="min-h-screen">
      <Topbar active="plaza" />
      <Toast message={notice} onClose={() => setNotice(null)} />

      <main className="w-full max-w-[1680px] mx-auto px-5 lg:px-8 py-6 pb-24">
        <header className="mb-5 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">广场</h1>
            <p className="text-sm text-ink-secondary mt-1.5">
              看看平台上正在发生什么。点一个人,让你的 Agent 先去试探。
            </p>
          </div>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="text-xs text-ink-secondary border border-line-soft rounded-md px-3 py-1.5 hover:border-ink-secondary disabled:opacity-50 transition"
          >
            {loading ? "刷新中" : "刷新"}
          </button>
        </header>

        {error && (
          <div className="bg-warn-soft text-warn rounded-md px-4 py-3 text-sm mb-4">
            {error}
          </div>
        )}

        {handoff && (
          <div className="mb-4 bg-primary-soft border border-primary/35 rounded-md px-4 py-3 flex items-center justify-between gap-3">
            <p className="text-sm text-primary-dark leading-relaxed">{handoff.message}</p>
            <Link
              href={handoff.href}
              className="text-xs font-medium text-primary-dark border border-primary/45 rounded-md px-3 py-1.5 hover:bg-bg transition whitespace-nowrap"
            >
              {handoff.label} →
            </Link>
          </div>
        )}

        <section className="relative h-[clamp(680px,76vh,960px)] bg-[#f7f9f8] border border-line-soft rounded-lg overflow-hidden shadow-card">
          <div className="absolute inset-0 bg-[linear-gradient(128deg,rgba(0,174,66,0.05),transparent_28%,rgba(14,165,233,0.035)_55%,transparent_82%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,249,248,0.78)_50%,rgba(255,255,255,0.98))]" />
          <div className="absolute inset-0 opacity-[0.18] bg-[linear-gradient(115deg,transparent_0%,transparent_46%,rgba(31,41,55,0.12)_46.2%,transparent_46.7%,transparent_100%)] bg-[length:180px_180px]" />
          <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-white/92 to-transparent" />
          <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-white/95 to-transparent" />
          <div className="absolute inset-0 shadow-[inset_0_30px_90px_rgba(31,41,55,0.035),inset_0_-28px_80px_rgba(0,174,66,0.055)]" />

          {loading && !feed && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-secondary">
              正在进入广场…
            </div>
          )}

          {plazaFeed && plazaFeed.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-secondary">
              广场还没人。先完成 .md,让你的 Agent 出现在这里。
            </div>
          )}

          {plazaFeed && (
            <>
              <div className="absolute inset-0 pointer-events-none">
                {fieldClouds.map(cloud => (
                  <FieldCloud key={cloud.label} cloud={cloud} />
                ))}
              </div>

              <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
                {fieldPulls.map(pull => (
                  <path
                    key={`${pull.user_id}-${pull.label}`}
                    d={fieldPullPath(pull)}
                    className={`fill-none stroke-primary ${pull.active ? "stroke-[0.34] opacity-[0.34]" : "stroke-[0.22] opacity-[0.10]"}`}
                    strokeDasharray={pull.active ? "0.9 1.5" : "0.6 2.4"}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
                {plazaFeed.links.map((link, idx) => {
                  const a = nodeById[link.source_user_id]
                  const b = nodeById[link.target_user_id]
                  if (!a || !b) return null
                  const linkedToSelf = selfUserId === link.source_user_id || selfUserId === link.target_user_id
                  const linkedToActive = !!activeUserId && (
                    activeUserId === link.source_user_id || activeUserId === link.target_user_id
                  )
                  if (!shouldRevealLink(link, idx, linkedToSelf, linkedToActive, !!activeUserId)) return null
                  return (
                    <path
                      key={`${link.source_user_id}-${link.target_user_id}`}
                      d={linkPath(a, b)}
                      className={linkClass(link.kind, linkedToSelf, linkedToActive, !!activeUserId)}
                      strokeDasharray={link.kind === "shallow_probe" ? "0.8 2.1" : undefined}
                      vectorEffect="non-scaling-stroke"
                    />
                  )
                })}
              </svg>

              <div className="absolute left-4 top-4 flex flex-wrap gap-2 text-[11px] text-ink-tertiary">
                <LegendDot label="游荡" />
                {visibleLinkKinds.has("shallow_probe") && (
                  <LegendLine label="浅层试探" kind="shallow_probe" />
                )}
                {visibleLinkKinds.has("deep_chat") && (
                  <LegendLine label="Agent 互聊" kind="deep_chat" />
                )}
                {visibleLinkKinds.has("human_chat") && (
                  <LegendLine label="真人聊天" kind="human_chat" />
                )}
              </div>

              {plazaFeed.nodes.map(node => (
                <PlazaPoint
                  key={node.user_id}
                  node={node}
                  selected={selected?.user_id === node.user_id}
                  active={activeUserId === node.user_id}
                  dimmed={!!activeUserId && activeUserId !== node.user_id && !activeRelatedIds.has(node.user_id)}
                  onSelect={() => {
                    setHoveredId(null)
                    setSelected(node)
                  }}
                  onHover={() => setHoveredId(node.user_id)}
                  onLeave={() => setHoveredId(current => current === node.user_id ? null : current)}
                />
              ))}

              <div className="absolute left-4 bottom-4 text-[11px] text-ink-tertiary">
                上次刷新 {new Date(plazaFeed.refreshed_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
              </div>
            </>
          )}
        </section>
      </main>

      {selected && (
        <ProfileDrawer
          node={selected}
          linkCount={plazaFeed?.links.filter(l =>
            l.source_user_id === selected.user_id || l.target_user_id === selected.user_id
          ).length || 0}
          selfLinkKind={selectedSelfLinkKind}
          initiating={initiatingId === selected.user_id}
          onClose={() => setSelected(null)}
          onInitiate={() => void initiate(selected)}
        />
      )}
    </div>
  )
}

function PlazaPoint({
  node,
  selected,
  active,
  dimmed,
  onSelect,
  onHover,
  onLeave,
}: {
  node: PlazaNode
  selected: boolean
  active: boolean
  dimmed: boolean
  onSelect: () => void
  onHover: () => void
  onLeave: () => void
}) {
  const hook = node.hooks[0]
  const showName = node.is_self || selected || active
  const showHook = selected || active
  const depth = nodeDepth(node)
  const pointSize = node.is_self ? 18 : selected || active ? 15 : Math.round(7 + depth * 5)
  const haloSize = node.is_self ? 12 : selected || active ? 9 : 5
  const drift = nodeDrift(node.user_id)
  return (
    <button
      onClick={onSelect}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      className={`absolute -translate-x-1/2 -translate-y-1/2 group text-left outline-none transition-opacity duration-300 ${
        dimmed ? "opacity-45 hover:opacity-100" : "opacity-100"
      }`}
      style={{
        left: `${node.x}%`,
        top: `${node.y}%`,
        zIndex: Math.round(10 + node.y),
        animation: `plaza-drift ${drift.duration}s ease-in-out ${drift.delay}s infinite alternate`,
      }}
      title={node.nickname}
    >
      <span className="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full" />
      {hook && (
        <span className={`absolute left-5 -top-8 whitespace-nowrap rounded-full border border-white/80 bg-white/[0.88] backdrop-blur px-3 py-1.5 text-[11px] text-ink-secondary shadow-[0_8px_24px_rgba(31,41,55,0.08)] transition ${
          showHook ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        }`}>
          {hook}
        </span>
      )}
      <span
        className={`relative flex items-center justify-center rounded-full transition duration-200 ${
          node.is_self
            ? "bg-primary shadow-[0_14px_32px_rgba(0,174,66,0.28)]"
            : selected || active
              ? "bg-primary-dark shadow-[0_10px_28px_rgba(0,174,66,0.22)]"
              : "bg-primary/75 shadow-[0_8px_22px_rgba(0,174,66,0.12)] group-hover:bg-primary"
        }`}
        style={{
          width: pointSize,
          height: pointSize,
          boxShadow: node.is_self
            ? `0 0 0 ${haloSize}px rgba(0,174,66,0.12),0 18px 38px rgba(0,174,66,0.28)`
            : `0 0 0 ${haloSize}px rgba(0,174,66,${selected || active ? 0.12 : 0.05}),0 10px 24px rgba(31,41,55,0.10)`,
        }}
      >
        {(node.state === "deep_chat" || node.state === "human_chat") && (
          <span className="absolute inset-[-7px] rounded-full border border-primary/30 animate-agent-pulse" />
        )}
      </span>
      <span className={`absolute left-1/2 top-5 -translate-x-1/2 whitespace-nowrap text-[11px] text-ink-secondary transition ${
        showName ? "opacity-100" : "opacity-0 group-hover:opacity-100"
      }`}>
        {node.is_self ? "你" : node.nickname}
      </span>
      {node.is_self && (
        <span className="absolute left-1/2 top-9 -translate-x-1/2 w-px h-7 bg-gradient-to-b from-primary/35 to-transparent" />
      )}
    </button>
  )
}

function ProfileDrawer({
  node,
  linkCount,
  selfLinkKind,
  initiating,
  onClose,
  onInitiate,
}: {
  node: PlazaNode
  linkCount: number
  selfLinkKind: PlazaLink["kind"] | null
  initiating: boolean
  onClose: () => void
  onInitiate: () => void
}) {
  const cta = getPlazaCta(node, initiating, selfLinkKind)
  const subject = pronounSubject(node.gender)
  const possessive = pronounPossessive(node.gender)
  return (
    <div className="fixed inset-0 z-[220] flex items-end justify-center px-4 pb-4 sm:items-center">
      <div className="absolute inset-0 z-0 bg-bg/72 backdrop-blur-md" onClick={onClose} />
      <aside className="relative z-10 w-full max-w-[460px] bg-bg rounded-lg border border-line-soft shadow-modal px-5 py-5">
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary" />
              <h2 className="text-lg font-semibold">@{node.nickname}</h2>
            </div>
            <p className="text-xs text-ink-tertiary mt-1.5">
              {compactMeta([node.age_band, genderLabel(node.gender), node.mbti])}
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-md text-ink-secondary hover:bg-bg-soft transition"
          >
            ×
          </button>
        </header>

        <div className="mt-5 space-y-4">
          <div>
            <div className="text-xs text-ink-tertiary mb-2">{subject}对外露出的钩子</div>
            <div className="flex flex-wrap gap-2">
              {(node.hooks.length ? node.hooks : ["还没冒泡"]).map(h => (
                <span key={h} className="rounded-full bg-bg-elevated border border-line-soft px-2.5 py-1 text-xs text-ink-secondary">
                  {h}
                </span>
              ))}
            </div>
          </div>

          <div>
            <div className="text-xs text-ink-tertiary mb-2">公开兴趣</div>
            <div className="flex flex-wrap gap-2">
              {(node.domains.length ? node.domains : ["还没填写"]).slice(0, 5).map(d => (
                <span key={d} className="rounded-md bg-primary-soft text-primary-dark px-2.5 py-1 text-xs">
                  {d}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-md bg-bg-elevated border border-line-soft px-3.5 py-3 text-sm text-ink-secondary leading-relaxed">
            {node.connection_label
              ? `${subject}更看重「${node.connection_label}」。这只是对外名片里的公开标签,具体的人还得让 Agent 去聊。`
              : `${possessive}公开名片还很轻。让 Agent 先去试探,比真人直接破冰省力。`}
          </div>

          <div className="flex items-center justify-between text-xs text-ink-tertiary border-t border-line-soft pt-3">
            <span>{getPlazaStatusLabel(node, selfLinkKind)}</span>
            <span>{linkCount > 0 ? `广场里有 ${linkCount} 条连接` : "暂时独自游荡"}</span>
          </div>
        </div>

        <footer className="mt-5">
          <button
            onClick={onInitiate}
            disabled={cta.disabled}
            className="w-full rounded-md bg-primary text-white py-3 text-sm font-medium hover:bg-primary-dark disabled:bg-line disabled:text-ink-tertiary disabled:cursor-not-allowed transition"
          >
            {cta.label}
          </button>
          {!node.is_self && (
            <p className="text-[11px] text-ink-tertiary leading-relaxed mt-2.5 text-center">
              聊完会回到个人房间生成简报。这里展示的是{possessive}对外名片,不是{possessive} .md 原文。
            </p>
          )}
          {node.is_self && (
            <Link href="/me" className="block text-center text-xs text-primary-dark mt-2.5 hover:underline underline-offset-2">
              去改我的资料
            </Link>
          )}
        </footer>
      </aside>
    </div>
  )
}

function getPlazaCta(
  node: PlazaNode,
  initiating: boolean,
  selfLinkKind: PlazaLink["kind"] | null,
): {
  label: string
  disabled: boolean
} {
  if (node.is_self) return { label: "这是你自己", disabled: true }
  if (initiating) return { label: "派出中…", disabled: true }
  if (selfLinkKind === "deep_chat") {
    return { label: "查看这场试探进展", disabled: false }
  }
  if (selfLinkKind === "human_chat") {
    return { label: "你们已经可以真人聊天", disabled: true }
  }
  return { label: `让我的 Agent 去${talkTargetText(node.gender)}`, disabled: false }
}

function getPlazaStatusLabel(
  node: PlazaNode,
  selfLinkKind: PlazaLink["kind"] | null,
): string {
  const subject = pronounSubject(node.gender)
  const object = pronounObject(node.gender)
  if (node.is_self) return "你在这里"
  if (selfLinkKind === "human_chat") return "你们已经开了真人聊天"
  if (selfLinkKind === "deep_chat") return `你的 Agent 已经试探过${object}`
  if (selfLinkKind === "shallow_probe") return `你已经试探过${object}`
  if (node.state === "human_chat") return `${subject}有一场真人聊天`
  if (node.state === "deep_chat") return `${subject}有一场 Agent 互聊`
  if (node.state === "shallow_probe") return `${subject}被试探过`
  return "游荡中"
}

function pronounSubject(gender?: string | null): string {
  if (gender === "female") return "她"
  if (gender === "male") return "他"
  return "TA "
}

function pronounObject(gender?: string | null): string {
  if (gender === "female") return "她"
  if (gender === "male") return "他"
  return " TA"
}

function pronounPossessive(gender?: string | null): string {
  if (gender === "female") return "她的"
  if (gender === "male") return "他的"
  return "TA 的"
}

function talkTargetText(gender?: string | null): string {
  if (gender === "female") return "跟她聊"
  if (gender === "male") return "跟他聊"
  return "跟 TA 聊"
}

function LegendDot({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg/80 border border-line-soft px-2 py-1">
      <span className="w-2 h-2 rounded-full bg-primary/75" />
      {label}
    </span>
  )
}

function LegendLine({ label, kind }: { label: string; kind: PlazaLink["kind"] }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg/80 border border-line-soft px-2 py-1">
      <svg width="22" height="6" viewBox="0 0 22 6" aria-hidden="true">
        <line
          x1="1"
          y1="3"
          x2="21"
          y2="3"
          className={linkClass(kind, false, true)}
          strokeDasharray={kind === "shallow_probe" ? "2 3" : undefined}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {label}
    </span>
  )
}

function FieldCloud({ cloud }: { cloud: FieldCloudView }) {
  const toneClass: Record<FieldCloudView["tone"], string> = {
    mint: "border-primary/15 text-primary-dark bg-primary/[0.035]",
    sky: "border-sky-500/15 text-sky-900 bg-sky-500/[0.035]",
    gold: "border-amber-500/18 text-amber-900 bg-amber-400/[0.045]",
    slate: "border-slate-400/18 text-slate-700 bg-slate-500/[0.035]",
  }
  return (
    <div
      className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border backdrop-blur-[2px] px-5 py-2.5 text-[11px] shadow-[0_18px_60px_rgba(31,41,55,0.055)] transition duration-300 ${
        cloud.active ? "scale-[1.04] border-primary/30 bg-white/78 text-primary-dark shadow-[0_22px_70px_rgba(0,174,66,0.12)]" : toneClass[cloud.tone]
      }`}
      style={{
        left: `${cloud.x}%`,
        top: `${cloud.y}%`,
        minWidth: cloud.width,
        opacity: cloud.active ? 0.92 : 0.52 + cloud.weight * 0.13,
      }}
    >
      {cloud.label}
    </div>
  )
}

function makeFieldClouds(nodes: PlazaNode[], activeNode: PlazaNode | null): FieldCloudView[] {
  const domains = topDomains(nodes)
  const activeDomains = new Set(activeNode?.domains.slice(0, DOMAIN_WEIGHTS.length) || [])
  return domains.map(({ label, score, count }, idx) => {
    const anchor = FIELD_ANCHORS[idx % FIELD_ANCHORS.length]
    return {
      label,
      x: anchor.x,
      y: anchor.y,
      width: 90 + Math.min(90, count * 18),
      tone: anchor.tone,
      weight: Math.min(1, score / 4),
      active: activeDomains.has(label),
    }
  })
}

function layoutPlazaFeed(feed: PlazaFeedResponse | null): PlazaFeedResponse | null {
  if (!feed) return null
  const self = feed.nodes.find(node => node.is_self)
  const selfUserId = self?.user_id || null
  const linkedToSelf = new Set<number>()
  feed.links.forEach(link => {
    if (!selfUserId) return
    if (link.source_user_id === selfUserId) linkedToSelf.add(link.target_user_id)
    if (link.target_user_id === selfUserId) linkedToSelf.add(link.source_user_id)
  })
  const nearIds = feed.nodes
    .filter(node => linkedToSelf.has(node.user_id))
    .map(node => node.user_id)
    .sort((a, b) => a - b)
  const nearIndex = new Map(nearIds.map((id, idx) => [id, idx]))
  const domainAnchors = domainAnchorMap(feed.nodes)
  const selfIndex = self ? feed.nodes.findIndex(node => node.user_id === self.user_id) : -1
  const selfField = self
    ? nodeFieldPosition(self, domainAnchors, Math.max(0, selfIndex))
    : { x: 52, y: 72 }
  const selfPosition = {
    x: clamp(selfField.x, 18, 82),
    y: clamp(selfField.y, 20, 80),
  }

  const positioned = feed.nodes.map((node, idx) => {
      if (node.is_self) {
        return { ...node, x: selfPosition.x, y: selfPosition.y }
      }

      const field = nodeFieldPosition(node, domainAnchors, idx)
      let x = field.x
      let y = field.y
      const near = nearIndex.get(node.user_id)
      if (near != null) {
        const orbit = nearFieldPosition(near, nearIds.length, node.user_id, selfPosition)
        x = mix(field.x, orbit.x, 0.68)
        y = mix(field.y, orbit.y, 0.68)
      }

      return {
        ...node,
        x: clamp(x, 8, 92),
        y: clamp(y, 13, 87),
      }
    })

  return {
    ...feed,
    nodes: spreadNodes(positioned),
  }
}

function topDomains(nodes: PlazaNode[]): Array<{ label: string; count: number; score: number }> {
  const counts = new Map<string, { count: number; score: number }>()
  nodes.forEach(node => {
    node.domains.slice(0, DOMAIN_WEIGHTS.length).forEach((domain, idx) => {
      const current = counts.get(domain) || { count: 0, score: 0 }
      counts.set(domain, {
        count: current.count + 1,
        score: current.score + (DOMAIN_WEIGHTS[idx] || 0.2),
      })
    })
  })
  return Array.from(counts.entries())
    .sort((a, b) => b[1].score - a[1].score || a[0].localeCompare(b[0], "zh-CN"))
    .slice(0, FIELD_ANCHORS.length)
    .map(([label, value]) => ({ label, count: value.count, score: value.score }))
}

function domainAnchorMap(nodes: PlazaNode[]): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>()
  topDomains(nodes).forEach(({ label }, idx) => {
    const anchor = FIELD_ANCHORS[idx % FIELD_ANCHORS.length]
    out.set(label, { x: anchor.x, y: anchor.y })
  })
  return out
}

function nodeFieldPosition(
  node: PlazaNode,
  domainAnchors: Map<string, { x: number; y: number }>,
  idx: number,
): { x: number; y: number } {
  const anchors = node.domains
    .slice(0, DOMAIN_WEIGHTS.length)
    .map((domain, domainIdx) => {
      const anchor = domainAnchors.get(domain)
      if (!anchor) return null
      return { ...anchor, weight: DOMAIN_WEIGHTS[domainIdx] || 0.2 }
    })
    .filter(Boolean) as Array<{ x: number; y: number; weight: number }>
  const fallbackAnchor = FIELD_ANCHORS[(stableNumber(`${node.user_id}:field`) + idx) % FIELD_ANCHORS.length]
  const weightSum = anchors.reduce((sum, a) => sum + a.weight, 0)
  const base = anchors.length
    ? {
      x: anchors.reduce((sum, a) => sum + a.x * a.weight, 0) / weightSum,
      y: anchors.reduce((sum, a) => sum + a.y * a.weight, 0) / weightSum,
    }
    : fallbackAnchor
  const angle = stableUnit(`${node.user_id}:field-angle`) * Math.PI * 2
  const range = 6 + Math.min(9, node.domains.length * 1.8)
  return {
    x: base.x + Math.cos(angle) * range + jitter(node.user_id, "x", 5.5),
    y: base.y + Math.sin(angle) * range * 0.78 + jitter(node.user_id, "y", 4.5),
  }
}

function makeFieldPulls(
  nodes: PlazaNode[],
  clouds: FieldCloudView[],
  activeUserId: number | null,
  activeRelatedIds: Set<number>,
  selfUserId: number | null,
): FieldPullView[] {
  const cloudByDomain = new Map(clouds.map(cloud => [cloud.label, cloud]))
  const pulls: FieldPullView[] = []
  nodes.forEach(node => {
    const isActive = activeUserId === node.user_id
    const isRelated = !!activeUserId && activeRelatedIds.has(node.user_id)
    const shouldShow = activeUserId
      ? isActive || isRelated
      : node.is_self || (node.featured && stableNumber(`${node.user_id}:field-pull`) % 4 === 0)
    if (!shouldShow) return

    node.domains.slice(0, isActive ? DOMAIN_WEIGHTS.length : 2).forEach((domain, idx) => {
      const cloud = cloudByDomain.get(domain)
      if (!cloud) return
      pulls.push({
        user_id: node.user_id,
        label: domain,
        x1: node.x,
        y1: node.y,
        x2: cloud.x,
        y2: cloud.y,
        active: isActive,
        strength: DOMAIN_WEIGHTS[idx] || 0.2,
      })
    })
  })
  return pulls.slice(0, activeUserId ? 22 : 10)
}

function nearFieldPosition(
  index: number,
  total: number,
  userId: number,
  center: { x: number; y: number },
): { x: number; y: number } {
  const span = Math.min(190, 48 + Math.max(0, total - 1) * 22)
  const start = 205 - span / 2
  const angle = (start + (span / Math.max(1, total - 1)) * index) * Math.PI / 180
  const rx = 28 + stableUnit(`${userId}:rx`) * 10
  const ry = 21 + stableUnit(`${userId}:ry`) * 8
  return {
    x: center.x + Math.cos(angle) * rx,
    y: center.y + Math.sin(angle) * ry,
  }
}

function spreadNodes(nodes: PlazaNode[]): PlazaNode[] {
  const out = nodes.map(node => ({ ...node }))
  const fixed = new Map(out.filter(node => node.is_self).map(node => [node.user_id, { x: node.x, y: node.y }]))
  const minDistance = 5.2
  const selfRepelDistance = 8.8

  for (let pass = 0; pass < 18; pass += 1) {
    for (let i = 0; i < out.length; i += 1) {
      for (let j = i + 1; j < out.length; j += 1) {
        const a = out[i]
        const b = out[j]
        const desired = a.is_self || b.is_self ? selfRepelDistance : minDistance
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01
        if (dist >= desired) continue

        const push = (desired - dist) * 0.5
        const nx = dx / dist
        const ny = dy / dist
        const aFixed = a.is_self
        const bFixed = b.is_self
        if (!aFixed) {
          a.x -= nx * push
          a.y -= ny * push
        }
        if (!bFixed) {
          b.x += nx * push
          b.y += ny * push
        }
      }
    }

    out.forEach(node => {
      const fixedPosition = fixed.get(node.user_id)
      if (fixedPosition) {
        node.x = fixedPosition.x
        node.y = fixedPosition.y
        return
      }
      node.x = clamp(node.x, 8, 92)
      node.y = clamp(node.y, 13, 87)
    })
  }

  return out
}

function mix(a: number, b: number, t: number): number {
  return a * (1 - t) + b * t
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function jitter(userId: number, salt: string, amount: number): number {
  return (stableUnit(`${userId}:${salt}`) - 0.5) * amount
}

function stableNumber(input: string): number {
  let hash = 0
  for (let i = 0; i < input.length; i += 1) {
    hash = (hash * 31 + input.charCodeAt(i)) % 9973
  }
  return hash
}

function stableUnit(input: string): number {
  return (stableNumber(input) % 1000) / 999
}

function shouldRevealLink(
  link: PlazaLink,
  index: number,
  linkedToSelf: boolean,
  linkedToActive: boolean,
  hasActive: boolean,
): boolean {
  if (hasActive) return linkedToActive
  if (linkedToSelf) return index % 2 === 0
  return link.kind === "human_chat" && index % 3 === 0
}

function linkPath(a: PlazaNode, b: PlazaNode): string {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const distance = Math.sqrt(dx * dx + dy * dy)
  const bend = Math.min(14, Math.max(4, distance * 0.18))
  const sign = (a.user_id + b.user_id) % 2 === 0 ? 1 : -1
  const nx = distance ? (-dy / distance) * bend * sign : 0
  const ny = distance ? (dx / distance) * bend * sign : 0
  const c1x = a.x + dx * 0.32 + nx
  const c1y = a.y + dy * 0.32 + ny
  const c2x = a.x + dx * 0.68 + nx
  const c2y = a.y + dy * 0.68 + ny
  return `M ${a.x} ${a.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${b.x} ${b.y}`
}

function fieldPullPath(pull: FieldPullView): string {
  const dx = pull.x2 - pull.x1
  const dy = pull.y2 - pull.y1
  const distance = Math.sqrt(dx * dx + dy * dy) || 0.01
  const curve = (5 + pull.strength * 5) * (pull.user_id % 2 === 0 ? 1 : -1)
  const nx = (-dy / distance) * curve
  const ny = (dx / distance) * curve
  const c1x = pull.x1 + dx * 0.42 + nx
  const c1y = pull.y1 + dy * 0.42 + ny
  const c2x = pull.x1 + dx * 0.72 + nx * 0.4
  const c2y = pull.y1 + dy * 0.72 + ny * 0.4
  return `M ${pull.x1} ${pull.y1} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${pull.x2} ${pull.y2}`
}

function linkClass(
  kind: PlazaLink["kind"],
  linkedToSelf = false,
  linkedToActive = false,
  hasActive = false,
): string {
  if (kind === "human_chat") {
    if (linkedToActive) return "fill-none stroke-[#047857] stroke-[0.92] opacity-[0.85]"
    if (linkedToSelf && !hasActive) return "fill-none stroke-[#047857] stroke-[0.62] opacity-[0.46]"
    return "fill-none stroke-[#047857] stroke-[0.42] opacity-[0.14]"
  }
  if (kind === "deep_chat") {
    if (linkedToActive) return "fill-none stroke-primary stroke-[0.52] opacity-[0.68]"
    if (linkedToSelf && !hasActive) return "fill-none stroke-primary stroke-[0.34] opacity-[0.34]"
    return "fill-none stroke-primary stroke-[0.24] opacity-[0.12]"
  }
  if (linkedToActive) return "fill-none stroke-ink-tertiary stroke-[0.28] opacity-[0.45]"
  if (linkedToSelf && !hasActive) return "fill-none stroke-ink-tertiary stroke-[0.22] opacity-[0.24]"
  return "fill-none stroke-ink-tertiary stroke-[0.16] opacity-[0.10]"
}

function nodeDepth(node: PlazaNode): number {
  return Math.min(1, Math.max(0, (node.y - 10) / 82))
}

function nodeDrift(userId: number): { duration: number; delay: number } {
  const base = 7 + (userId % 5)
  return {
    duration: base,
    delay: -1 * (userId % 7),
  }
}

function genderLabel(g?: string | null): string | null {
  return ({
    female: "女",
    male: "男",
    non_binary: "非二元",
    prefer_not_to_say: "不愿透露",
  } as Record<string, string>)[g || ""] || null
}

function compactMeta(parts: Array<string | null | undefined>): string {
  const out = parts.filter(Boolean)
  return out.length ? out.join(" · ") : "公开资料很少"
}
