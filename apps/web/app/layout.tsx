import type { Metadata } from 'next'
import AgentFloatingWidget from '@/components/AgentFloatingWidget'
import MockUserBanner from '@/components/MockUserBanner'
import ReleaseNoteModal from '@/components/ReleaseNoteModal'
import './globals.css'

export const metadata: Metadata = {
  title: 'CyberMOMO',
  description: 'AI 先行社交平台 · 先聊的不是你',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body className="font-sans">
        {children}
        {/* 全站右下:跟自己 Agent 聊;onboarding 等流程内自动隐藏 */}
        <AgentFloatingWidget />
        {/* 有新版本时自动弹一次;onboarding 流程内跳过 */}
        <ReleaseNoteModal />
        {/* Phase 1+ OAuth 接入后删除 */}
        <MockUserBanner />
      </body>
    </html>
  )
}
