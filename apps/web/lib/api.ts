/**
 * API client · MVP 阶段 mock auth(X-Mock-User-Id 头)
 *
 * 用法:
 *   const me = await api.get<UserMe>("/api/auth/me")
 *   const md = await api.post<MdResponse, CreateMdReq>("/api/md", { profile })
 *
 * OAuth 接入后只换 `getAuthHeader()` 实现,业务代码不动。
 */

const BASE = process.env.NEXT_PUBLIC_API_URL || ""

const MOCK_USER_KEY = "cybermomo_mock_user_id"

export function getMockUserId(): string {
  if (typeof window === "undefined") return "1"
  return window.localStorage.getItem(MOCK_USER_KEY) || "1"
}

export function setMockUserId(id: string | number) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(MOCK_USER_KEY, String(id))
}

function getAuthHeader(): Record<string, string> {
  // MVP 阶段:mock auth 头
  // OAuth 接入后换为 Authorization Bearer 或 cookie 走默认凭证
  return { "X-Mock-User-Id": getMockUserId() }
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`${status}: ${detail}`)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${BASE}${path}`
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
  }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }
  const resp = await fetch(url, init)
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
  email: string
  google_name?: string | null
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
}

export interface RoomStatusResponse {
  chatting_count: number
  spark_count: number
  total_summaries_pending: number
  top_hint?: { nickname?: string | null; topic?: string | null } | null
}

export interface DecisionRequest {
  decision: "open_human_chat" | "re_dispatch" | "drop" | "chat_with_my_agent"
}

export interface ChatSessionResponse {
  id: number
  match_id: number
  user_a_id: number
  user_b_id: number
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
