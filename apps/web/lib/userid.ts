/**
 * user_id 编码 · 给用户展示的"标识"不要直接是数字
 *
 * 动机:DB 里 User.id 是 auto-increment BigInteger。前端任何地方直接展示
 * 数字 ID(比如 /me 页面 "user_id 29") = 一眼看出当前平台用户规模(也能
 * 推断注册顺序、新用户数变化等)。MVP 阶段不想暴露这些信号。
 *
 * 设计选择:
 * - 纯客户端不可逆 hash(murmur3 finalizer 风格)
 * - 同一个 numeric id 永远映射到同样的 hash —— 用户能稳定识别自己 / 别人
 * - 短(6 字符)、无歧义字母表(去掉 0/o/1/l 等容易看混)
 * - 不可逆:看 hash 推不回 numeric id,也猜不出"我前面有多少人"
 * - 不需要 server 配合 / migration,纯 cosmetic
 *
 * **不是安全屏障**:server API / URL 路径仍用数字 id,只是显示层模糊化。
 * 真要做防枚举需要 server 加 short_code 字段(后续可选)。
 */

// 30-char 字母表:数字 2-9 + 小写字母去掉 i/l/o(避免 1/I/L/0/O 看混)
const ALPHA = "23456789abcdefghjkmnpqrstuvwxyz"
const ALPHA_LEN = ALPHA.length // 30
const HASH_LEN = 6

/**
 * 数字 user_id → 6 字符稳定 hash。
 *
 * 用 murmur3 finalizer 做 mixing —— 简短、雪崩效应好、纯 JS bitwise 实现。
 * 连续 id(29, 30, 31...)经过 mixing 后 hash 看起来完全无规律。
 */
export function encodeUserId(id: number | null | undefined): string {
  if (id == null || !Number.isFinite(id) || id <= 0) return "??????"
  // JS 坑:位运算(XOR / shift)结果是 signed int32,负数 % 30 在 JS 里返回负数,
  // ALPHA[负数] = undefined。每步 XOR 后强制 `>>> 0` 转 unsigned。
  let h = (id * 0x9e3779b1) >>> 0 // golden ratio mult(扩散低位)
  h = (h ^ (h >>> 16)) >>> 0
  h = Math.imul(h, 0x85ebca6b) >>> 0
  h = (h ^ (h >>> 13)) >>> 0
  h = Math.imul(h, 0xc2b2ae35) >>> 0
  h = (h ^ (h >>> 16)) >>> 0

  let s = ""
  for (let i = 0; i < HASH_LEN; i++) {
    s = ALPHA[h % ALPHA_LEN] + s
    h = Math.floor(h / ALPHA_LEN)
  }
  return s
}

/**
 * 给"展示用户标识"统一前缀,方便 UI 一眼识别这是个 ID 不是别的。
 * 例:`u-x4mz7k`
 */
export function displayUserId(id: number | null | undefined): string {
  return `u-${encodeUserId(id)}`
}
