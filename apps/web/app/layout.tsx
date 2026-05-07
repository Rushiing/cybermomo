import type { Metadata } from 'next'
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
      <body className="font-sans">{children}</body>
    </html>
  )
}
