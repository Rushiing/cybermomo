import type { Config } from 'tailwindcss'

/**
 * CyberMOMO 设计 tokens
 * 基于 cybermomo/交互拆解/_设计调性.md v0
 *
 * 米白纸感 + 拓竹绿撞色 + 极简克制
 */
const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // 米白底
        bg: {
          DEFAULT: '#FAF8F3',
          elevated: '#FFFFFF',
          soft: '#F0EDE5',
        },
        // 文字
        ink: {
          DEFAULT: '#1F2937',
          secondary: '#6B7280',
          tertiary: '#9CA3AF',
        },
        // 边框
        line: {
          DEFAULT: '#E5E7EB',
          soft: '#EDEAE3',
        },
        // 主题色 · 拓竹绿
        primary: {
          DEFAULT: '#00AE42',
          soft: '#E6F5EB',
          dark: '#008C35',
        },
        // 警告 · 重动作红
        warn: {
          DEFAULT: '#DC2626',
          soft: '#FEE2E2',
        },
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '20px',
      },
      fontFamily: {
        sans: [
          'Inter',
          '"Noto Sans SC"',
          '"PingFang SC"',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(0, 0, 0, 0.04)',
        modal: '0 12px 40px rgba(0, 0, 0, 0.12)',
        fab: '0 4px 16px rgba(0, 0, 0, 0.10)',
        drawer: '0 -4px 32px rgba(0, 0, 0, 0.10)',
      },
      keyframes: {
        pulse: {
          '0%, 100%': { transform: 'scale(1)', opacity: '0.4' },
          '50%': { transform: 'scale(1.4)', opacity: '0' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'agent-pulse': 'pulse 2.4s ease-in-out infinite',
        'fade-in': 'fadeIn 250ms ease forwards',
      },
    },
  },
  plugins: [],
}

export default config
