"use client"

/**
 * 广场 placeholder · 还没动工
 *
 * 设计中:像素点社交生态 + 关键词钩子气泡 + 主动派 Agent。
 * 现在保持极简,别给用户错觉。
 */
import Topbar from "@/components/Topbar"

export default function PlazaPage() {
  return (
    <div className="min-h-screen">
      <Topbar active="plaza" />
      <main className="max-w-[640px] mx-auto px-6 py-32 text-center">
        <p className="text-lg text-ink-secondary">
          🧱 建设中…再等等等等等等等等
        </p>
      </main>
    </div>
  )
}
