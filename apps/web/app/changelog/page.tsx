"use client"

/**
 * /changelog · 完整更新日志
 *
 * 数据来源:apps/web/lib/releaseNotes.ts
 * 格式约定:【发布日期 + 更新内容】,用户视角描述功能变化
 */
import Link from "next/link"
import { useEffect } from "react"

import Topbar from "@/components/Topbar"
import {
  LATEST_VERSION,
  RELEASE_NOTES,
  markVersionSeen,
} from "@/lib/releaseNotes"

export default function ChangelogPage() {
  // 用户主动来看更新日志时,就把"已看过最新版本"标上,避免之后再弹
  useEffect(() => {
    if (LATEST_VERSION) markVersionSeen(LATEST_VERSION)
  }, [])

  return (
    <div className="min-h-screen">
      <Topbar active="me" />

      <main className="max-w-[640px] mx-auto px-6 py-8 pb-24">
        <header className="mb-8">
          <Link href="/me" className="text-xs text-ink-secondary hover:text-ink mb-3 inline-flex items-center gap-1">
            ← 返回我的
          </Link>
          <h1 className="text-xl font-semibold mt-2">更新日志</h1>
          <p className="text-sm text-ink-tertiary mt-1.5 leading-relaxed">
            CyberMOMO 的每次迭代,你能感受到什么变化。
          </p>
        </header>

        {RELEASE_NOTES.length === 0 && (
          <p className="text-center py-12 text-ink-secondary">还没有更新记录。</p>
        )}

        <div className="space-y-10">
          {RELEASE_NOTES.map(entry => (
            <article key={entry.version} className="border-l-2 border-primary-soft pl-5">
              <div className="text-xs text-ink-tertiary tracking-[0.04em] mb-1.5">
                【{entry.date}】
              </div>
              {entry.title && (
                <h2 className="text-base font-semibold leading-snug mb-4">{entry.title}</h2>
              )}

              <div className="space-y-5">
                {entry.sections.map((sec, i) => (
                  <section key={i}>
                    {sec.category && (
                      <h3 className="text-xs text-ink-secondary tracking-[0.04em] mb-2.5">{sec.category}</h3>
                    )}
                    <ul className="space-y-2.5">
                      {sec.bullets.map((b, j) => (
                        <li key={j} className="text-[14px] leading-relaxed text-ink">
                          {b}
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
            </article>
          ))}
        </div>
      </main>
    </div>
  )
}
