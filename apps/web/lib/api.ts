/**
 * API client · 走 session cookie(OAuth 后),dev 模式有 mock 头 fallback
 *
 * 用法:
 *   const me = await api.get<UserMe>("/api/auth/me")
 *   const md = await api.post<MdResponse, CreateMdReq>("/api/md", { profile })
 *
 * 所有请求都带 credentials: 'include',浏览器会自动带上 cm_session cookie。
 * dev 模式额外发 X-Mock-User-Id(后端在 cookie 缺失时 fallback 到这个头)。
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || ""

// 仅 dev 模式打开 mock auth header — prod build 时 NEXT_PUBLIC_DEV_MOCK_AUTH 不设
// 就不会发出 X-Mock-User-Id,完全依赖 cookie
const DEV_MOCK_AUTH =
  (process.env.NEXT_PUBLIC_DEV_MOCK_AUTH || "true").toLowerCase() === "true"

const MOCK_USER_KEY = "cybermomo_mock_user_id"

export function getMockUserId(): string {
  if (typeof window === "undefined") return "1"
  return window.localStorage.getItem(MOCK_USER_KEY) || "1"
}

export function setMockUserId(id: string | number) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(MOCK_USER_KEY, String(id))
}

export function isDevMockAuth(): boolean {
  return DEV_MOCK_AUTH
}

function getAuthHeader(): Record<string, string> {
  // Cookie 自动走 credentials: 'include',这里只在 dev 模式下加 mock 头作 fallback
  // 后端 deps:cookie 优先,cookie 没读到才看 mock 头
  if (!DEV_MOCK_AUTH) return {}
  return { "X-Mock-User-Id": getMockUserId() }
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`)
  }
}

/**
 * Railway 单 worker 偶发拥塞会让浏览器 fetch 直接抛 TypeError("Failed to fetch")。
 * 这跟 server 返 4xx/5xx 不一样:fetch 根本没拿到 HTTP 响应 — 多半是连接被
 * 拒/重置或者 TCP layer 异常。这种情况 retry 是安全的(idempotent or not 都没
 * 真到 server),不会重复扣副作用。
 *
 * 4xx/5xx 不重试 — 那是 server 真的返了,语义已经发生。
 */
const FETCH_RETRY_DELAYS_MS = [800, 2500]  // 总最坏 ~3.3s + 实际 fetch 时间

async function _fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  let lastErr: unknown = null
  for (let attempt = 0; attempt <= FETCH_RETRY_DELAYS_MS.length; attempt++) {
    try {
      return await fetch(url, init)
    } catch (e: any) {
      lastErr = e
      // 只重试网络层错(TypeError);AbortError(用户取消)不重试
      const isAbort = e?.name === "AbortError"
      const isNetwork = e instanceof TypeError
      if (isAbort || !isNetwork || attempt >= FETCH_RETRY_DELAYS_MS.length) {
        throw e
      }
      // backoff 后继续
      await new Promise(r => setTimeout(r, FETCH_RETRY_DELAYS_MS[attempt]))
    }
  }
  throw lastErr
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${BASE}${path}`
  const init: RequestInit = {
    method,
    credentials: "include",  // 关键:浏览器带上 session cookie 跨域请求
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
  }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }
  const resp = await _fetchWithRetry(url, init)
  const text = await resp.text()
  let data: any = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText
    throw new ApiError(resp.status, detail)
  }
  return data as T
}

/**
 * SSE 流式调用 helper(给 /api/me/agent/conversations/{id}/messages 用)
 *
 * 服务端格式:
 *   event: token
 *   data: <增量>
 *
 *   event: done
 *   data: {"conversation_id": N}
 *
 *   event: error
 *   data: <错误信息>
 *
 * 用法:
 *   await streamSSE("/api/me/agent/...", { content: "..." }, {
 *     onToken: tok => setText(t => t + tok),
 *     onDone:  () => setStreaming(false),
 *     onError: msg => setError(msg),
 *     signal:  abortController.signal,
 *   })
 */
export interface StreamSSEHandlers {
  onToken: (token: string) => void
  onDone?: (data: string) => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

export async function streamSSE(
  path: string,
  body: unknown,
  handlers: StreamSSEHandlers,
): Promise<void> {
  const url = `${BASE}${path}`
  const resp = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...getAuthHeader(),
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
  })
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => "")
    const detail = text || resp.statusText
    throw new ApiError(resp.status, detail)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buf = ""
  // 单个 event 的累积字段
  let currentEvent: string | null = null
  let currentData: string[] = []

  function flushEvent() {
    if (currentEvent === null && currentData.length === 0) return
    const data = currentData.join("\n")
    if (currentEvent === "token") handlers.onToken(data)
    else if (currentEvent === "done") handlers.onDone?.(data)
    else if (currentEvent === "error") handlers.onError?.(data)
    currentEvent = null
    currentData = []
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })

    // 按行处理(SSE event 以空行分隔)
    let nlIdx: number
    while ((nlIdx = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, nlIdx).replace(/\r$/, "")
      buf = buf.slice(nlIdx + 1)
      if (line === "") {
        // 空行 = event 边界
        flushEvent()
      } else if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        currentData.push(line.slice(5).replace(/^\s/, ""))
      }
      // 其它(comment / id 等)忽略
    }
  }
  // tail
  if (buf.length > 0) {
    // 流尾如果还有残留 data 行,按一个 event 收尾
    if (currentEvent !== null || currentData.length > 0) flushEvent()
  } else {
    flushEvent()
  }
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T, B = unknown>(path: string, body?: B) => request<T>("POST", path, body),
  put: <T, B = unknown>(path: string, body?: B) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
}

// ========================================
// Type definitions(后端 schema 镜像;后续可用 OpenAPI 自动生成)
// ========================================

export interface UserMeResponse {
  id: number
  email?: string | null
  username?: string | null
  google_name?: string | null
  google_avatar_url?: string | null
  is_adult_confirmed: boolean
  onboarded_at?: string | null
  created_at: string
  profile?: {
    nickname: string
    age_band?: string | null
    gender?: string | null
    mbti?: string | null
    avatar_url?: string | null
  } | null
}

export interface UpsertProfileRequest {
  profile: {
    nickname: string
    age_band?: string | null
    gender?: string | null
    mbti?: string | null
    avatar_url?: string | null
  }
}

export interface RegisterRequest {
  username: string  // 3-20,字母数字下划线
  password: string  // 8-100
  email?: string | null
  nickname?: string | null
}

export interface LoginRequest {
  username: string
  password: string
}

export interface CreateMdRequest {
  profile: any  // v3 完整 profile JSON
}

export interface MdDocumentResponse {
  id: number
  user_id: number
  version: number
  profile_version: string
  domains_interested: string[]
  domains_avoided: string[]
  portrait_title: string
  portrait_body: string[]
  is_active: boolean
  created_at: string
}

export interface SummaryResponse {
  id: number
  agent_chat_id?: number | null
  chat_session_id?: number | null
  host_user_id: number
  summary_type: string
  verdict: string
  highlights: { text: string; evidence_utterance_id?: number | null }[]
  risks: { text: string; evidence_utterance_id?: number | null }[]
  recommended_action: string
  evidence_chunks: { utterance_id: number; speaker: string; text: string }[]
  created_at: string
  user_decision?: string | null
  decided_at?: string | null
  // 这张简报关于谁(前端卡片标题用)
  peer_user_id?: number | null
  peer_nickname?: string | null
  // 仅决策 chat_with_my_agent 的响应里出现 — 用于跳转 /me/agent/{id}
  agent_conversation_id?: number | null
}

export interface RoomStatusResponse {
  chatting_count: number
  spark_count: number
  total_summaries_pending: number
  top_hint?: { nickname?: string | null; topic?: string | null } | null
}

export interface DecisionRequest {
  // 注:chat_with_my_agent 已不再是 decision(走 /api/summary/{id}/agent-chat)
  decision: "open_human_chat" | "re_dispatch" | "drop"
  // 仅 re_dispatch 时使用 — 跟 Agent 在对话里沉淀的方向 hint
  direction_hint?: string | null
}

export interface ChatSessionResponse {
  id: number
  match_id: number
  source_summary_id?: number | null  // 从哪张简报衍生(旧 session 可能 NULL)
  user_a_id: number
  user_b_id: number
  user_a_nickname?: string | null
  user_b_nickname?: string | null
  status: string
  last_message_at?: string | null
  created_at: string
}

export interface ChatMessageResponse {
  id: number
  session_id: number
  sender_user_id: number
  content_type: "text" | "image"
  content: string
  sent_at: string
}

export interface ChatBriefingResponse {
  summary_id: number
  verdict: string
  highlights: { text: string; evidence_utterance_id?: number | null }[]
  risks: { text: string; evidence_utterance_id?: number | null }[]
  recommended_action: string
  evidence_chunks: { utterance_id: number; speaker: string; text: string }[]
  created_at: string
}

export interface CalloutRequest {
  callout_prompt: string
  context_message_ids?: number[]
}

export interface CalloutResponse {
  id: number
  session_id: number
  callout_prompt: string
  callout_response: string
  context_message_ids?: number[] | null
  model: string
  created_at: string
}

export interface AgentChatMessageView {
  id: number
  speaker: "host" | "peer"
  turn: number
  topic_ref: string
  intent: string
  utterance: string
  public_signals: Record<string, any>
  own_private_signals?: Record<string, any> | null
}

export interface AgentChatViewResponse {
  agent_chat_id: number
  status: string
  end_reason?: string | null
  turns: number
  messages: AgentChatMessageView[]
}

// ========================================
// 跟自己 Agent 对话(§4.10)
// ========================================

export type AgentConversationScope = "room" | "plaza" | "revisit" | "general"

export interface AgentConversation {
  id: number
  host_user_id: number
  scope: AgentConversationScope
  title?: string | null
  context_refs?: Record<string, any> | null
  last_message_at?: string | null
  created_at: string
  last_message_preview?: string | null
}

export interface AgentConversationMessage {
  id: number
  conversation_id: number
  role: "user" | "assistant" | "system"
  content: string
  turn: number
  created_at: string
}

export interface CreateAgentConversationRequest {
  scope?: AgentConversationScope
  title?: string | null
  context_refs?: Record<string, any> | null
}

