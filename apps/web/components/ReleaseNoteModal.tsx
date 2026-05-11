"use client"

/**
 * 最新版本弹窗 — 用户没看过最新版本时,自动弹一次。
 * 在 layout.tsx 挂全局;onboarding/quiz 等首次流程页面里不要打扰用户,
 * 用 disablePaths 跳过(/onboarding* /md/quiz* /md/basic* /md/review* /md/generating)。
 */
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"

import {
  LATEST_NOTE,
  markVersionSeen,
  shouldShowReleaseModal,
} from "@/lib/releaseNotes"

const DISABLED_PATH_PREFIXES = [
  "/onboarding",
  "/md/quiz",
  "/md/basic",
  "/md/review",
  "/md/generating",
]

function isDisabledPath(pathname: string | null): boolean {
  if (!pathname) return true
  // 登录页 / 首屏不打扰
  if (pathname === "/") return true
  // onboarding 流程也跳过(新用户还没体验产品就看更新日志会困惑)
  return DISABLED_PATH_PREFIXES.some(p => pathname.startsWith(p))
}

export default function ReleaseNoteModal() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (isDisabledPath(pathname)) return
    if (shouldShowReleaseModal()) setOpen(true)
  }, [pathname])

  function close() {
    if (LATEST_NOTE) markVersionSeen(LATEST_NOTE.version)
    setOpen(false)
  }

  if (!open || !LATEST_NOTE) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={close} />

      <div className="relative bg-bg rounded-lg shadow-modal max-w-lg w-full max-h-[85vh] flex flex-col">
        <header className="px-6 py-5 border-b border-line-soft flex-shrink-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-primary" />
            <span className="text-xs text-primary-dark font-medium tracking-[0.04em]">有新更新</span>
          </div>
          <div className="text-[11px] text-ink-tertiary mb-1">【{LATEST_NOTE.date}】</div>
          {LATEST_NOTE.title && (
            <h2 className="text-lg font-semibold leading-snug">{LATEST_NOTE.title}</h2>
          )}
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {LATEST_NOTE.sections.map((sec, i) => (
            <section key={i}>
              {sec.category && (
                <h3 className="text-xs text-ink-secondary tracking-[0.04em] mb-2.5">{sec.category}</h3>
              )}
              <ul className="space-y-2.5">
                {sec.bullets.map((b, j) => (
                  <li key={j} className="text-[14px] leading-relaxed text-ink pl-3 border-l-2 border-primary-soft">
                    {b}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        <footer className="px-6 py-4 border-t border-line-soft flex-shrink-0 flex items-center justify-between gap-3">
          <Link
            href="/changelog"
            onClick={close}
            className="text-xs text-ink-secondary hover:text-ink underline-offset-2 hover:underline"
          >
            看完整更新日志 →
          </Link>
          <button
            onClick={close}
            className="bg-primary text-white px-5 py-2 rounded-full font-medium text-sm hover:bg-primary-dark transition"
          >
            知道了
          </button>
        </footer>
      </div>
    </div>
  )
}
