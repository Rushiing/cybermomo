/**
 * Release notes · 用户视角的更新日志
 *
 * 维护规则:
 * - 数组顺序:最新的放第一个
 * - version:用 ISO 日期(YYYY-MM-DD)即可,localStorage 拿来比对"用户上次看过的版本"
 * - 内容:**全部用用户视角描述**(他能感受到的功能变化),不是工程实现
 * - 弹窗只弹数组第一个(LATEST_VERSION)的内容
 * - 更新日志页 /changelog 展示全部
 */

export interface ReleaseSection {
  /** "新功能" "体验改进" "修复" 等,可空 */
  category?: string
  bullets: string[]
}

export interface ReleaseEntry {
  /** 版本标识 — 用 ISO 日期即可 */
  version: string
  /** 展示用日期 */
  date: string
  /** 一行标题(可空)— 整次发布的主线 */
  title?: string
  /** 按 category 分组的内容 */
  sections: ReleaseSection[]
}

export const RELEASE_NOTES: ReleaseEntry[] = [
  {
    version: "2026-05-11b",
    date: "2026-05-11",
    title: "你可以直接跟自己 Agent 对话了",
    sections: [
      {
        category: "新功能",
        bullets: [
          "右下角浮动 Agent — 全站都能点开,跟你的 Agent 直接聊。它知道你的 .md 人格,记得过去那些简报,能基于这些跟你讨论。",
          "「跟我 Agent 聊聊」真的能聊了 — 简报上点这个决策,直接进入对话页,Agent 会引用那张简报起头。",
          "Agent 主动回访 — 真人聊天结束后(或被对方拉黑、24h 没动静),Agent 会主动起一段对话:「跟你简单同步下,刚那场怎么样?」 在「我」→「跟我的 Agent 聊过什么」里能找到。",
          "「我」→ 设置里新增「跟我的 Agent 聊过什么」入口,所有跟 Agent 的会话历史在一起看。",
        ],
      },
      {
        category: "看不见但发生了什么",
        bullets: [
          "Agent 能从你过去的简报里检索相关记忆 — 你问它「user_3 跟我合适吗」,它会从那场互聊和简报里调出来跟你聊。",
          "Agent 跟你说话的风格是「朋友式八卦」,不是客服 — 它可以有理有据反驳你的决定,但最终方向你定。",
        ],
      },
    ],
  },
  {
    version: "2026-05-11",
    date: "2026-05-11",
    title: "Agent 互聊更顺滑 · 聊过的人都看得到",
    sections: [
      {
        category: "新功能",
        bullets: [
          "「Agent 替我聊过谁」总览 — 「我」里新增了一段,所有 Agent 替你聊过的场次都能回看。对方 Agent 的内部信号按铁律不展示。",
          "「看看 Agent 们都聊了什么」回放 — 简报展开后多了一个入口,能看到双方 Agent 的完整对话。",
          "「再派一次」真的能再派了 — 简报上点击,Agent 会真的换个话题再跟 TA 聊一场,大约一分钟回来给你新简报。旧场会标记成「已换话题再派」,不会丢。",
          "简报和真人聊天打通了 — 真人聊天卡上能看到是源自哪张简报(点击会回到那张高亮一下);简报卡上也能直接进入对应的聊天室。",
          "新增「更新日志」入口 — 在「我」→ 设置里看完整版本历史。以后每次有新功能上线,会自动弹一次告诉你。",
        ],
      },
      {
        category: "体验改进",
        bullets: [
          "Agent 聊得更精炼了 — Agent 替你跟别人聊天会更早摸到关键点,不再东拉西扯。",
          "真人聊天入口直接在「房间」里 — 不用再手动改 URL 找入口。",
          "重要提示用柔和的提示条 — 不再弹浏览器原生提示框。",
        ],
      },
    ],
  },
  {
    version: "2026-05-07",
    date: "2026-05-07",
    title: "CyberMOMO 测试期上线",
    sections: [
      {
        category: "开始用",
        bullets: [
          "你可以从注册开始走完一整套流程:注册 → 问卷生成 .md 档案 → 自动匹配 → Agent 替你跟别人聊 → 看简报决策(开聊 / 再派 / 丢 / 跟我 Agent 聊聊)→ 真人聊天(聊不下去随时叫 Agent 帮忙)→ 退出 / 拉黑 / 举报 → Agent 给你一份观察报告。",
          "你的 .md 档案永远不会被别人看到 — 这是平台铁律,不会因为任何匹配或推荐而暴露。",
        ],
      },
    ],
  },
]

export const LATEST_VERSION = RELEASE_NOTES[0]?.version ?? ""
export const LATEST_NOTE = RELEASE_NOTES[0] ?? null

const STORAGE_KEY = "cybermomo_seen_release_v"

/** 浏览器本地存储:用户看过的最新版本 */
export function getSeenVersion(): string | null {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(STORAGE_KEY)
}

export function markVersionSeen(version: string) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(STORAGE_KEY, version)
}

/** 是否应该弹窗:用户没看过最新版本 */
export function shouldShowReleaseModal(): boolean {
  if (typeof window === "undefined") return false
  if (!LATEST_VERSION) return false
  return getSeenVersion() !== LATEST_VERSION
}
