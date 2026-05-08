"use client"

/**
 * 广场 placeholder · MVP 阶段产品形态待讨论
 *
 * 后续真正实装见 cybermomo/DEMO/mvp/08-plaza.html v3 prototype
 */
import Link from "next/link"

import Topbar from "@/components/Topbar"

export default function PlazaPage() {
  return (
    <div className="min-h-screen">
      <Topbar active="plaza" />

      <main className="max-w-[640px] mx-auto px-6 py-16 text-center">
        <div className="w-16 h-16 mx-auto mb-6 rounded-full border-[1.5px] border-dashed border-primary bg-primary-soft flex items-center justify-center">
          <span className="w-3 h-3 rounded-full bg-primary" />
        </div>
        <h1 className="text-2xl font-semibold mb-3">广场暂未开放</h1>
        <p className="text-ink-secondary leading-relaxed max-w-md mx-auto mb-8">
          产品形态(像素点社交生态 + 关键词钩子气泡 + 主动派 Agent 浅层试探)正在内部讨论。
          MVP 第一轨 — 平台自动匹配 + Agent 互聊 + 简报卡 — 已经跑通,可以先用。
        </p>
        <Link href="/room" className="inline-block bg-primary text-white px-7 py-3 rounded-full font-medium hover:bg-primary-dark transition">
          回个人房间
        </Link>
        <p className="text-xs text-ink-tertiary mt-8">
          预览:<a href="../../../DEMO/mvp/08-plaza.html" className="underline">vault DEMO/mvp/08-plaza.html</a>
        </p>
      </main>
    </div>
  )
}
