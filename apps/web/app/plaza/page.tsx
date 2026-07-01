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

export default function PlazaPage() {
  const [feed, setFeed] = useState<PlazaFeedResponse | null>(null)
  const [selected, setSelected] = useState<PlazaNode | null>(null)
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
      await load()
    } catch (e: any) {
      setNotice(e?.detail || e?.message || "这次没派出去,稍后再试。")
    } finally {
      setInitiatingId(null)
    }
  }

  const nodeById = useMemo(() => {
    const out: Record<number, PlazaNode> = {}
    feed?.nodes.forEach(n => { out[n.user_id] = n })
    return out
  }, [feed])
  const selfUserId = useMemo(
    () => feed?.nodes.find(n => n.is_self)?.user_id || null,
    [feed],
  )
  const selectedSelfLinkKind = useMemo(() => {
    if (!feed || !selected || !selfUserId) return null
    return feed.links.find(link =>
      (link.source_user_id === selfUserId && link.target_user_id === selected.user_id)
      || (link.target_user_id === selfUserId && link.source_user_id === selected.user_id)
    )?.kind || null
  }, [feed, selected, selfUserId])

  return (
    <div className="min-h-screen">
      <Topbar active="plaza" />
      <Toast message={notice} onClose={() => setNotice(null)} />

      <main className="max-w-[1040px] mx-auto px-5 py-6 pb-24">
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

        <section className="relative h-[680px] min-h-[calc(100vh-180px)] bg-bg-elevated border border-line-soft rounded-lg overflow-hidden shadow-card">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,174,66,0.08),transparent_34%),linear-gradient(rgba(31,41,55,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(31,41,55,0.035)_1px,transparent_1px)] bg-[length:100%_100%,56px_56px,56px_56px]" />

          {loading && !feed && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-secondary">
              正在进入广场…
            </div>
          )}

          {feed && feed.nodes.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-secondary">
              广场还没人。先完成 .md,让你的 Agent 出现在这里。
            </div>
          )}

          {feed && (
            <>
              <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
                {feed.links.map(link => {
                  const a = nodeById[link.source_user_id]
                  const b = nodeById[link.target_user_id]
                  if (!a || !b) return null
                  return (
                    <line
                      key={`${link.source_user_id}-${link.target_user_id}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      className={linkClass(link.kind)}
                      strokeDasharray={link.kind === "shallow_probe" ? "1.8 1.8" : undefined}
                      vectorEffect="non-scaling-stroke"
                    />
                  )
                })}
              </svg>

              <div className="absolute left-4 top-4 flex flex-wrap gap-2 text-[11px] text-ink-tertiary">
                <LegendDot label="游荡" />
                <LegendLine label="浅层试探" className="border-dashed" />
                <LegendLine label="Agent 互聊" className="border-solid border-primary" />
                <LegendLine label="真人聊天" className="border-double border-primary" />
              </div>

              {feed.nodes.map(node => (
                <PlazaPoint
                  key={node.user_id}
                  node={node}
                  selected={selected?.user_id === node.user_id}
                  onSelect={() => setSelected(node)}
                />
              ))}

              <div className="absolute left-4 bottom-4 text-[11px] text-ink-tertiary">
                上次刷新 {new Date(feed.refreshed_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}
              </div>
            </>
          )}
        </section>
      </main>

      {selected && (
        <ProfileDrawer
          node={selected}
          linkCount={feed?.links.filter(l =>
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
  onSelect,
}: {
  node: PlazaNode
  selected: boolean
  onSelect: () => void
}) {
  const hook = node.hooks[0]
  const showLabel = node.featured || selected
  return (
    <button
      onClick={onSelect}
      className="absolute -translate-x-1/2 -translate-y-1/2 group text-left"
      style={{ left: `${node.x}%`, top: `${node.y}%` }}
      title={node.nickname}
    >
      {hook && (
        <span className={`absolute left-5 -top-8 whitespace-nowrap rounded-md border border-line-soft bg-bg-elevated px-2.5 py-1.5 text-[11px] text-ink-secondary shadow-card transition ${
          showLabel ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        }`}>
          {hook}
        </span>
      )}
      <span className={`relative flex items-center justify-center rounded-full transition ${
        node.is_self
          ? "w-5 h-5 bg-primary shadow-[0_0_0_7px_rgba(0,174,66,0.14)]"
          : selected
            ? "w-4 h-4 bg-primary-dark shadow-[0_0_0_6px_rgba(0,174,66,0.12)]"
            : "w-3 h-3 bg-primary/80 group-hover:bg-primary"
      }`}>
        {(node.state === "deep_chat" || node.state === "human_chat") && (
          <span className="absolute inset-[-5px] rounded-full border border-primary/40 animate-agent-pulse" />
        )}
      </span>
      <span className={`absolute left-1/2 top-5 -translate-x-1/2 whitespace-nowrap text-[11px] text-ink-secondary transition ${
        showLabel ? "opacity-100" : "opacity-0 group-hover:opacity-100"
      }`}>
        {node.is_self ? "你" : node.nickname}
      </span>
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
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center px-4 pb-4 sm:items-center">
      <div className="absolute inset-0 bg-ink/25 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative w-full max-w-[460px] bg-bg rounded-lg border border-line-soft shadow-modal px-5 py-5">
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
            <div className="text-xs text-ink-tertiary mb-2">TA 对外露出的钩子</div>
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
              ? `TA 更看重「${node.connection_label}」。这只是对外名片里的公开标签,具体的人还得让 Agent 去聊。`
              : "TA 的公开名片还很轻。让 Agent 先去试探,比真人直接破冰省力。"}
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
              聊完会回到个人房间生成简报。这里展示的是 TA 的对外名片,不是 TA 的 .md 原文。
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
  return { label: "让我的 Agent 去跟 TA 聊", disabled: false }
}

function getPlazaStatusLabel(
  node: PlazaNode,
  selfLinkKind: PlazaLink["kind"] | null,
): string {
  if (node.is_self) return "你在这里"
  if (selfLinkKind === "human_chat") return "你们已经开了真人聊天"
  if (selfLinkKind === "deep_chat") return "你的 Agent 已经试探过 TA"
  if (selfLinkKind === "shallow_probe") return "你已经试探过 TA"
  if (node.state === "human_chat") return "TA 有一场真人聊天"
  if (node.state === "deep_chat") return "TA 有一场 Agent 互聊"
  if (node.state === "shallow_probe") return "TA 被试探过"
  return "游荡中"
}

function LegendDot({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg/80 border border-line-soft px-2 py-1">
      <span className="w-2 h-2 rounded-full bg-primary/75" />
      {label}
    </span>
  )
}

function LegendLine({ label, className }: { label: string; className: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-bg/80 border border-line-soft px-2 py-1">
      <span className={`w-5 border-t ${className}`} />
      {label}
    </span>
  )
}

function linkClass(kind: PlazaLink["kind"]): string {
  if (kind === "human_chat") return "stroke-primary stroke-[0.55] opacity-80"
  if (kind === "deep_chat") return "stroke-primary stroke-[0.42] opacity-60"
  return "stroke-ink stroke-[0.24] opacity-25"
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
