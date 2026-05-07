/**
 * v3 灵魂快照 · 题库 + 规则引擎(完整 port from /Users/xihe/Desktop/人格画像问卷_v3.html)
 *
 * 17 题 + 21 领域 → profile JSON
 * 完全 deterministic,纯前端跑(< 100ms)
 */

// ========================================
// AREAS · 21 领域(P1 兴趣 + P2 回避)
// ========================================

export const AREAS = [
  "AI与科技", "心理与人类观察", "商业财经", "设计审美", "时尚形象",
  "文学写作", "影视综艺", "音乐演出", "游戏", "二次元动漫",
  "健身运动", "体育赛事", "历史社科", "时政公共议题", "旅行城市",
  "生活方式", "家居美食", "教育学习", "情感关系", "神秘学与命理",
  "其他",
] as const

export type Area = typeof AREAS[number]

// ========================================
// Question schema
// ========================================

export type QuestionScale = 4 | 5 | "tag"

export interface Question {
  id: string
  title: string
  text: string
  note?: string
  options: string[]
  scale: QuestionScale
  tags?: string[]
  codes?: string[]
}

// ========================================
// Q · 17 道题(完全 mirror v3 source)
// ========================================

export const Q: Question[] = [
  { id: "E1", title: "社交后的能量变化", text: "一次普通聚会结束后,过程没有尴尬、冲突,也不是被迫营业。", note: "请先假设你已经参加了,不用考虑你一开始愿不愿意去,只回答\"参加之后\"的能量变化。", options: ["明显被消耗,只想独处恢复","有点累,需要缓一缓","还好,没有明显变化","有点兴奋,状态被带起来了","意犹未尽,还想继续聊或继续见人"], scale: 5 },
  { id: "E3", title: "分享欲", text: "你遇到一件让自己很开心的事,这件事和别人没有直接关系。\n不考虑有没有合适的人可说,只看你当下是否会自然产生分享冲动。", options: ["通常不会产生想分享的念头","偶尔会想说,但不说也没什么","会想分享,但只在刚好有机会时说","会明显想找人分享","会很想马上说出来,不说会憋得慌"], scale: 5 },
  { id: "O3", title: "观点冲突", text: "你和一个关系不深不浅的人聊天时,发现对方对同一件事的看法和你完全不同。\n这不是道德问题,也不涉及底线,只是观点差异很大。", note: "这里只看你面对非底线观点差异时的探索兴趣,不判断你是否同意对方,也不要求你说服对方。\n这里的\"关系不深不浅\"是指普通但有一定互动基础的人,不要只代入\"完全不熟所以无所谓\",也不要只代入\"很亲密所以很在意\"。", options: ["会抗拒继续听,想避开这个话题","不太想深入,觉得知道对方不同意就够了","可以听听,但不会主动追问","会有点好奇,想知道对方为什么这么想","会很想深入聊下去,享受这种观点碰撞和探索感"], scale: 5 },
  { id: "CMM1", title: "日常关心方式", text: "一个你在意的朋友最近状态似乎有点低落,但 ta 没有正式找你倾诉,也没有明确求助。\n你比较自然的反应是?", options: ["会当作对方自己的状态处理,不太会特别关注","会注意到,但先保持距离,等对方自己开口","会轻轻问一句,给 ta 一个开口的机会","会主动靠近,明确表达关心和陪伴"], scale: 4, tags: ["低介入关心","留意但克制","轻触式关心","明确陪伴型"], codes: ["low_intervention","attentive_reserved","gentle_check_in","active_warmth"] },
  { id: "CMM2", title: "别人来倾诉", text: "有朋友向你倾诉一件让 ta 不舒服的事。\nta 刚开始讲,你还不知道完整经过,也不需要你马上做决定。\n\n你第一时间更容易被什么牵引?", note: "这里只看你面对倾诉开头时的第一反应,不判断哪种方式更好。", options: ["想先弄清楚事情经过、逻辑和问题卡点","想先确认 ta 到底希望我分析、建议,还是单纯听 ta 说","想先接住 ta 的情绪,让 ta 感觉自己被理解"], scale: "tag", tags: ["问题理解型","需求确认型","情绪承接型"], codes: ["problem_mapping","need_checking","emotional_holding"] },
  { id: "CMM3", title: "你更珍惜哪种连接", text: "在关系深度和相处时间差不多的情况下,\n哪一种连接最容易让你觉得\"这段关系对我很重要\"?", note: "这里只看哪一种连接最容易让你珍惜关系,不是问哪一种关系更高级,也不是说你只能需要一种。", options: ["协作连接:我们能一起推进事情、解决问题、把事做成。关系的重要感来自\"我们配合得起来\"。","共鸣连接:我们有相似的兴趣、审美、表达方式或脑回路,常常会有\"你也这样?\"\"我也是!\"的同频感。","理解连接:ta 不一定和我一样,但能准确明白我为什么会这样想、这样感受、这样反应。","陪伴连接:ta 会稳定地在我的生活里,让我感觉被惦记、被陪着、不是一个人。"], scale: "tag", tags: ["协作连接","共鸣连接","理解连接","陪伴连接"], codes: ["collaborative_connection","resonance_connection","mutual_understanding_connection","companionship_connection"] },
  { id: "AU2", title: "节奏被打断", text: "你正在按自己的节奏待着,可能是在休息、做事、刷东西、发呆,或者只是想一个人荒废时间。\n一个你熟悉但不亲密的人,经常临时把你拉进一些小互动里:问你意见、让你一起决定、希望你马上回应。\n这些事本身不烦,也不重要,但会反复打断你原本的状态。", note: "请代入\"熟悉但不亲密的人\",不要代入最亲密的人或刚认识的人。", options: ["很舒服,喜欢这种随时被拉进互动的感觉","大多可以接受,不太觉得被打断","偶尔会觉得被打断,但还能接受","会有点压力,希望对方少临时打断我","会明显不舒服,很想保护自己的时间和节奏"], scale: 5 },
  { id: "AV3", title: "关系变近后的压力", text: "一段你在意的关系自然变近了。\n对方开始更频繁地和你分享情绪,也更希望你回应、解释自己的状态、参与彼此的生活。\n对方没有强迫你,也没有做错,只是关系确实比以前更近了。", note: "请优先代入恋人关系;如果当前没有恋人,请代入你最在意、最亲近、最容易牵动你情绪的人。如果现实中没有完全对应的人,请想象一种\"你确实很在意对方\"的亲密关系。这里只问你的自然反应,不判断你实际会怎么做。", options: ["会更放松,觉得关系变近是好事","大多是舒服的,也愿意多回应一点","有时会觉得不太习惯,但整体还能接受","会有点想退回原来的距离,减少这种密度","会明显有压力,想重新拉开距离"], scale: 5 },
  { id: "AX2", title: "对方突然冷一点", text: "在一段你很在意的关系里,对方平时回复和互动都比较稳定。\n今天 ta 突然明显话少了,也没有解释。", note: "请优先代入恋人关系;如果当前没有恋人,请代入你最在意、最亲近、最容易牵动你情绪的人。如果现实中没有完全对应的人,请想象一种\"你确实很在意对方\"的亲密关系。这里只问你的自然反应,不判断你实际会怎么做。", options: ["基本不受影响","会注意到,但不太会多想","会有点在意,想知道 ta 是不是遇到什么事","会开始想是不是关系里哪里不对","会明显不安,很想确认原因"], scale: 5 },
  { id: "AU1", title: "被安排", text: "有一件原本该由你自己决定的小事,时间不紧,也没有明显压力。\n有人出于方便,提前替你安排好了。\n这个安排本身没有明显坏处,也不涉及控制、讨好或恶意。", note: "请先假设这不是紧急情况,也不是对方在帮你减轻重大负担。", options: ["很舒服,省心了","基本可以接受","可以接受,但会希望下次先问我","有点不舒服,还是想自己决定","明显不舒服,我需要自己掌控节奏"], scale: 5 },
  { id: "CON4", title: "承诺前的谨慎", text: "别人请你帮一个忙。\n你愿意帮,但现在只有六七成把握能做到。\n对方希望知道能不能把这件事交给你。", note: "这里只看你在把握不足时,愿意给出多强的承诺,不是测你愿不愿意帮忙。", options: ["\"可以,交给我。\"","\"应该可以,我会尽量弄好。\"","\"我可以试试,但不保证一定成。\"","\"我先不答应,等我确认能做到再回复你。\"","\"现在没把握,我不能接。\""], scale: 5 },
  { id: "CON2", title: "迟到且没有提前说", text: "你和别人约好了时间。\n对方迟到了二十分钟,而且在迟到前没有提前告诉你;事后才解释原因。", options: ["几乎不在意,临时变动没有提前说也能接受","会有点不舒服,但如果事后原因合理,很快就过去","会明确介意\"没提前说\"这一点,希望对方下次至少提前告知","会比较影响我对 ta 可靠性的判断,觉得这不是小事","会明显觉得这不尊重约定,之后会减少对 ta 的信任"], scale: 5 },
  { id: "ES3", title: "被误解时", text: "别人误解了你的意思,而且语气不太好。\n你第一时间的内心反应更接近?", options: ["情绪会立刻被带起来,很难冷静回应","会明显不舒服,容易急着反驳或解释","会受影响,但还能尽量把话说清楚","会先稳住情绪,再解释或澄清","基本不被带走,能冷静判断要不要回应"], scale: 5 },
  { id: "ES2", title: "情绪恢复速度", text: "遇到一件让你明显不舒服、但没有严重到改变现实后果的事。\n比如被误解、被否定、计划被打乱,或者一次让你很不爽的互动。\n\n这种不舒服的感觉,通常会在你心里持续多久?", note: "这里问的是\"不舒服感自然变淡的速度\",不是问你能不能继续做事,也不是问你表面上能不能维持正常。", options: ["几天以上:几天后想起来,还是会明显不舒服","一天左右:通常到第二天,甚至更久,才慢慢变淡","半天左右:通常要到当天晚些时候,才明显变淡","几个小时内:通常几个小时内,会明显变淡","半小时以内:通常半小时以内,就明显变淡"], scale: 5 },
  { id: "O4", title: "陌生体验", text: "朋友邀请你尝试一个你从没接触过的新活动。\n它安全,成本不高,也不涉及你明确讨厌的领域,只是你完全没试过。", note: "这里不是强制邀请,只看你对\"新体验本身\"的反应。", options: ["抗拒","没什么兴趣","有一点点想知道会是什么样","挺想体验一下","会因为\"没试过\"这件事本身就很想去"], scale: 5 },
  { id: "D1", title: "没人推进时", text: "几个人一起讨论一个轻量但需要做决定的事,比如去哪吃饭、怎么玩、怎么分工。\n没人指定你负责,但现场有点散,事情推不动。", note: "请代入普通社交场景里的轻量共同决定,不是工作考核、上下级分工、利益得失或奖金惩罚。这里只看你面对散乱局面时的自然反应。", options: ["会抗拒自己来推进,哪怕有点乱也不想承担这个角色","不会主动推进,但如果有人带头,我会配合","会轻微补一句,帮大家把话题拉回决定上","会主动帮大家整理选项和下一步","会自然接过组织和推进的角色,带大家定下来"], scale: 5 },
  { id: "D2", title: "有把握时的坚持", text: "几个人在讨论接下来怎么做时出现分歧。\n这不是道德问题,也没有现实利益冲突,但会影响下一步行动。\n你有八成把握自己的判断更合适。", note: "请先假设大家是平等关系,对这个项目或行动共同主导、共同负责。这里测的是行动决策中的主导倾向,不是单纯观点争论,也不是上下级关系。", options: ["不太想坚持,觉得按别人说的来也行","会简单说一下,但大家不同意就算了","会把理由说清楚,但不执着于让大家采用","会比较想让大家理解并认真考虑我的判断","会明显想把自己的判断立住,推动大家按这个方向走"], scale: 5 },
]

// ========================================
// Profile types
// ========================================

export interface ProfilePortrait {
  title: string
  main_type: string
  title_reason: string
  core_tension: string
  tags: string[]
  body: string[]
  debug: any
}

export interface Profile {
  meta: { version: string; generated_at: string }
  domains: { interested: string[]; avoided: string[] }
  raw_answers: Record<string, { option_index: number | null; option_text: string | null }>
  dialogue: any
  relationship_warmth: any
  boundary_and_closeness: any
  reliability: any
  conflict_repair: any
  exploration: any
  agency: any
  portrait: ProfilePortrait
}

// ========================================
// 计算工具
// ========================================

export function score(idx: number, scale: QuestionScale): number | null {
  if (scale === 4) return Math.round((idx / 3) * 100)
  if (scale === 5) return Math.round((idx / 4) * 100)
  return null
}

const high = (v: number | null) => v !== null && v >= 67
const low = (v: number | null) => v !== null && v <= 34

function val(ans: Record<string, number>, id: string): number | null {
  const q = Q.find(x => x.id === id)
  if (!q) return null
  const i = ans[id]
  if (i === undefined) return null
  return score(i, q.scale)
}

function txt(ans: Record<string, number>, id: string): string | null {
  const q = Q.find(x => x.id === id)
  if (!q) return null
  const i = ans[id]
  if (i === undefined) return null
  return q.options[i]
}

function tg(ans: Record<string, number>, id: string) {
  const q = Q.find(x => x.id === id)
  if (!q) return { label: "", code: null, option_index: 0 }
  const i = ans[id]
  return {
    label: q.tags ? q.tags[i] : q.options[i],
    code: q.codes ? q.codes[i] : null,
    option_index: i + 1,
  }
}

// ========================================
// Feature 抽取(top strongest features)
// ========================================

interface Feature {
  key: string
  value?: number | null
  polarity?: string
  strength: number
  label: string
  text: string
}

function featurePolarity(
  key: string,
  value: number | null,
  lowLabel: string, highLabel: string,
  lowText: string, highText: string,
): Feature {
  if (value === null) return { key, value: null, polarity: "mid", strength: 0, label: "", text: "" }
  const strength = Math.abs(value - 50)
  if (value < 50) return { key, value, polarity: "low", strength, label: lowLabel, text: lowText }
  if (value > 50) return { key, value, polarity: "high", strength, label: highLabel, text: highText }
  return { key, value, polarity: "mid", strength: 0, label: "", text: "" }
}

function strongestFeatures(p: any): Feature[] {
  const d = p.dialogue, b = p.boundary_and_closeness, r = p.reliability, c = p.conflict_repair, e = p.exploration, a = p.agency, w = p.relationship_warmth
  const features: Feature[] = [
    featurePolarity("social_energy", d.social_energy, "低频社交", "社交充电", "你不是靠频繁见人恢复能量的人,社交对你来说更像一种需要选择性投入的资源。", "你比较容易在互动里被带起来,社交会让你的状态变得更鲜活。"),
    featurePolarity("sharing_drive", d.sharing_drive, "低分享欲", "高分享欲", "你不太需要通过分享来确认关系,很多开心或有趣的事自己消化也可以。", "你有明显的表达火花,遇到开心、有趣、兴奋的事,会自然想让别人也知道。"),
    featurePolarity("disagreement_exploration", d.disagreement_exploration, "回避观点碰撞", "观点探索", "你不太想把普通关系里的聊天推向分歧和碰撞,舒服、顺畅比争出深度更重要。", "你对不同观点背后的原因有兴趣,不急着让对方和你一致,反而会想理解差异从哪里来。"),
    featurePolarity("interruption_sensitivity", b.interruption_sensitivity, "低打断敏感", "强节奏边界", "你比较能接受别人临时把你拉进互动,日常小来回不太会让你觉得被侵犯。", "你对临时插入式互动很敏感,尤其不喜欢别人默认你随时可以回应。"),
    featurePolarity("arranged_decision_discomfort", b.arranged_decision_discomfort, "接受被安排", "自主感强", "别人提前替你安排小事时,你多数会觉得省心,而不是被控制。", "你很在意选择权。即使安排本身没有坏处,别人没问过就替你决定,也会让你不舒服。"),
    featurePolarity("closeness_density_pressure", b.closeness_density_pressure, "亲密放松", "亲密密度压力", "关系自然变近通常会让你更放松,你不太会因为亲密本身感到压迫。", "关系变近后,如果回应、解释、参与彼此生活的密度上升太快,你会有后撤压力。"),
    featurePolarity("coldness_sensitivity", b.coldness_sensitivity, "低冷淡敏感", "关系温差敏感", "对方短暂变冷通常不太会动摇你,你更容易先按现实原因理解。", "你很容易捕捉到对方突然变冷,这会牵动你对关系稳定性的判断。"),
    featurePolarity("commitment_caution", r.commitment_caution, "承诺随性", "承诺谨慎", "你比较容易先接住请求,再在过程中调整。", "你不太会在没把握时轻易承诺。你更愿意先确认,再负责。"),
    featurePolarity("notice_expectation", r.notice_expectation, "变动宽容", "重视提前说明", "你对临时变化比较宽松,不太会因为一次没提前说就立刻降低信任。", "你很在意\"提前说\"。变动本身未必最严重,真正影响你的是对方没有交代。"),
    featurePolarity("misunderstanding_regulation", c.misunderstanding_regulation, "容易被误解点燃", "误解时能稳住", "被误解且对方语气不好时,你容易立刻被带起来,急着反驳或澄清。", "被误解时,你比较能先稳住,再决定要不要解释。"),
    featurePolarity("emotional_recovery_speed", c.emotional_recovery_speed, "情绪留痕久", "恢复速度快", "不舒服感容易在心里停留,哪怕表面上已经恢复正常。", "不舒服感来得快,淡得也比较快。"),
    featurePolarity("novelty_seeking", e.novelty_seeking, "新体验谨慎", "新体验趋近", "你对陌生体验比较谨慎,不会因为\"新\"本身就想尝试。", "你对安全、低成本的新体验有趋近感,会被\"没试过\"这件事吸引。"),
    featurePolarity("task_initiation", a.task_initiation, "低推进", "自然推进", "你不太喜欢默认自己来组织局面,哪怕事情有点散,也未必想接过推进角色。", "当一群人散着聊、没人推进时,你会自然把事情往前拉。"),
    featurePolarity("decision_assertiveness", a.decision_assertiveness, "低判断坚持", "判断有立场", "即使你有自己的判断,也不一定执着于让大家采用。", "当你对判断有把握时,会希望别人认真考虑你的方向,而不是随便折中。"),
  ]
  const tagFeatures: Feature[] = [
    {
      key: "warmth_initiation", strength: 38, label: w.warmth_initiation.label,
      text: ({
        low_intervention: "你表达关心的方式偏克制。即使注意到对方不太对劲,也不一定会马上介入。",
        attentive_reserved: "你会留意对方的状态,但通常会先观察,避免太快越界。",
        gentle_check_in: "你比较擅长轻轻打开一个入口,让对方知道自己可以说。",
        active_warmth: "你在关系里会比较主动地释放关心,让对方感到自己被惦记。",
      } as Record<string, string>)[w.warmth_initiation.code || ""] || "",
    },
    {
      key: "support_style", strength: 34, label: w.support_style.label,
      text: ({
        problem_mapping: "别人来倾诉时,你容易先进入\"理解问题结构\"的模式。",
        need_checking: "别人来倾诉时,你会先判断对方到底需要建议、分析,还是单纯被听见。",
        emotional_holding: "别人来倾诉时,你会先接住情绪,而不是马上分析对错。",
      } as Record<string, string>)[w.support_style.code || ""] || "",
    },
    {
      key: "connection_value", strength: 42, label: w.connection_value.label,
      text: ({
        collaborative_connection: "你会通过一起做事、一起推进、一起解决问题来确认关系的价值。关系的重要感来自\"我们配合得起来\"。",
        resonance_connection: "你容易被同频感吸引:相似的兴趣、审美、表达方式或脑回路,会让关系快速变重要。",
        mutual_understanding_connection: "你最容易被\"准确理解\"打动。对方不一定和你一样,但能明白你为什么这样想、这样感受、这样反应。",
        companionship_connection: "你很看重稳定在场。持续惦记、稳定陪着,会让你觉得自己不是一个人。",
      } as Record<string, string>)[w.connection_value.code || ""] || "",
    },
  ]
  return [...features, ...tagFeatures].filter(x => x.text).sort((x, y) => y.strength - x.strength)
}

// ========================================
// Combo rules(50+,完全镜像 v3)
// ========================================

interface ComboRule {
  keys: string[]
  weight: number
  type: "core" | "tension" | "hidden" | "risk" | "strength" | "texture"
  text: string
}

function addComboRules(p: any, strongest: Set<string>): ComboRule[] {
  const out: ComboRule[] = []
  const d = p.dialogue, b = p.boundary_and_closeness, r = p.reliability, c = p.conflict_repair, a = p.agency, e = p.exploration, w = p.relationship_warmth
  const conn = w.connection_value.code, support = w.support_style.code, warmth = w.warmth_initiation.code

  const R = (rule: ComboRule) => {
    let bonus = 0
    rule.keys.forEach(k => { if (strongest.has(k)) bonus += 14 })
    out.push({ ...rule, weight: rule.weight + bonus })
  }

  if (low(d.social_energy) && high(d.sharing_drive)) R({ keys:["social_energy","sharing_drive"], weight:95, type:"core", text:"你不是没有分享欲,而是社交续航和表达冲动不总是同步。开心、兴奋、有意思的东西会让你很想说出来,但这不代表你愿意一直在线、一直互动。" })
  if (high(d.social_energy) && low(d.sharing_drive)) R({ keys:["social_energy","sharing_drive"], weight:80, type:"texture", text:"你可以进入热闹,也能被互动带起来,但你未必习惯把自己的开心事、私密感受主动摊开。你更像是\"能聊\",但不一定\"爱自我暴露\"。" })
  if (low(d.social_energy) && low(d.sharing_drive)) R({ keys:["social_energy","sharing_drive"], weight:85, type:"core", text:"你对社交的默认需求比较低,也不太需要通过分享来确认关系。很多事情你自己消化就可以,除非对方真的足够重要或足够合拍。" })
  if (high(d.social_energy) && high(d.sharing_drive)) R({ keys:["social_energy","sharing_drive"], weight:85, type:"core", text:"你比较容易在互动里被点燃,也会自然用分享延续关系。对你来说,聊天不是单纯交换信息,而是让状态流动起来。" })
  if (low(d.social_energy) && high(d.disagreement_exploration)) R({ keys:["social_energy","disagreement_exploration"], weight:92, type:"core", text:"你的社交入口不宽,但思考入口很深。你未必想频繁见人,但一旦话题进入观点、动机、立场背后的原因,你会明显更有兴趣。" })
  if (high(d.social_energy) && high(d.disagreement_exploration)) R({ keys:["social_energy","disagreement_exploration"], weight:78, type:"texture", text:"你既能进入互动,也能承受一定观点碰撞。只要氛围不是攻击性的,你会把差异当成理解对方的入口,而不是马上避开的风险。" })
  if (high(d.sharing_drive) && high(b.coldness_sensitivity)) R({ keys:["sharing_drive","coldness_sensitivity"], weight:88, type:"tension", text:"你分享时其实很需要回应感。你不只是把事情说出去,而是在看对方有没有接住。如果对方突然冷一点,你会很容易感到自己的热情落空。" })
  if (high(b.closeness_density_pressure) && high(b.coldness_sensitivity)) R({ keys:["closeness_density_pressure","coldness_sensitivity"], weight:98, type:"core", text:"这是你关系里很关键的一组矛盾:你需要稳定回应带来的安全感,但当关系真的变得很密、很频繁、很需要解释和参与时,你又会想后撤。你要的不是忽远忽近,而是稳定但有呼吸感的靠近。" })
  if (low(b.closeness_density_pressure) && high(b.coldness_sensitivity)) R({ keys:["closeness_density_pressure","coldness_sensitivity"], weight:82, type:"core", text:"你其实愿意亲密,也不太抗拒关系自然变近。真正让你不安的不是靠近本身,而是对方靠近之后又突然冷掉。" })
  if (high(b.closeness_density_pressure) && low(b.coldness_sensitivity)) R({ keys:["closeness_density_pressure","coldness_sensitivity"], weight:76, type:"texture", text:"你对亲密密度有压力,但不太会因为对方短暂变冷就强烈不安。你更在意自己的空间有没有被保留,而不是对方每一刻是否稳定回应。" })
  if (high(b.interruption_sensitivity) && high(b.closeness_density_pressure)) R({ keys:["interruption_sensitivity","closeness_density_pressure"], weight:94, type:"core", text:"你对\"关系侵入感\"比较敏感。不是不能亲近,而是不喜欢亲近变成频繁打断、即时回应、随时解释自己的状态。" })
  if (high(b.interruption_sensitivity) && low(b.closeness_density_pressure)) R({ keys:["interruption_sensitivity","closeness_density_pressure"], weight:78, type:"hidden", text:"你并不排斥亲密本身,但很在意亲密发生的方式。只要对方尊重你的节奏,不突然插入或打断,你其实可以很放松地靠近。" })
  if (low(b.interruption_sensitivity) && high(b.closeness_density_pressure)) R({ keys:["interruption_sensitivity","closeness_density_pressure"], weight:72, type:"hidden", text:"你可以接受日常小互动,但当关系升级到更深的情绪参与、状态解释和生活卷入时,你才会感到压力。你抗拒的不是打扰,而是亲密责任变重。" })
  if (high(b.arranged_decision_discomfort) && high(b.interruption_sensitivity)) R({ keys:["arranged_decision_discomfort","interruption_sensitivity"], weight:90, type:"core", text:"你对自主感很敏感。别人替你安排、临时拉你回应、默认你会配合,都会让你感觉自己的节奏被拿走。" })
  if (conn === "mutual_understanding_connection" && high(b.interruption_sensitivity)) R({ keys:["connection_value","interruption_sensitivity"], weight:90, type:"tension", text:"你很需要被理解,但理解不能以\"随时进入你的生活\"为代价。你想被懂,而不是被过度读取、过度参与。" })
  if (conn === "companionship_connection" && high(b.interruption_sensitivity)) R({ keys:["connection_value","interruption_sensitivity"], weight:88, type:"tension", text:"你重视陪伴,但这种陪伴最好是稳定在场,而不是频繁打断。你喜欢\"我在\",不喜欢\"你现在必须回应我\"。" })
  if (conn === "resonance_connection" && high(d.disagreement_exploration)) R({ keys:["connection_value","disagreement_exploration"], weight:86, type:"core", text:"你要的同频不是永远意见一致,而是能在差异里继续理解彼此。能聊审美、观点、世界观的人,会让你很快产生连接感。" })
  if (conn === "collaborative_connection" && high(a.task_initiation)) R({ keys:["connection_value","task_initiation"], weight:84, type:"core", text:"你很容易在一起做事的过程中建立关系。对你来说,关系不只靠聊天升温,也靠一起推进、互相配合、把事情落地。" })
  if (warmth === "active_warmth" && high(b.arranged_decision_discomfort)) R({ keys:["warmth_initiation","arranged_decision_discomfort"], weight:82, type:"hidden", text:"你可以主动关心别人,但不代表你喜欢别人用同样主动的方式替你决定。你给出的温暖是陪伴,不是接管。" })
  if (warmth === "low_intervention" && high(b.coldness_sensitivity)) R({ keys:["warmth_initiation","coldness_sensitivity"], weight:80, type:"hidden", text:"你自己关心别人时可能偏克制,但在重要关系里,你却会留意对方是否变冷。这说明你不是不在意,只是表达和感受不对称。" })
  if (support === "emotional_holding" && conn === "mutual_understanding_connection") R({ keys:["support_style","connection_value"], weight:84, type:"core", text:"你很重视感受被接住。对你来说,真正的理解不是给出正确分析,而是在情绪上让人感觉\"我不是一个人\"。" })
  if (high(r.commitment_caution) && high(r.notice_expectation)) R({ keys:["commitment_caution","notice_expectation"], weight:92, type:"core", text:"你对可靠性的理解很清楚:没把握就不要随便答应,有变化就提前说明。你不一定要求别人完美,但很在意对方是否尊重预期。" })
  if (high(c.misunderstanding_regulation) && low(c.emotional_recovery_speed)) R({ keys:["misunderstanding_regulation","emotional_recovery_speed"], weight:90, type:"hidden", text:"你表面上可能能稳住,甚至能讲道理,但这不代表你心里很快过去。别人容易低估你内部消化的时间。" })
  if (low(c.misunderstanding_regulation) && low(c.emotional_recovery_speed)) R({ keys:["misunderstanding_regulation","emotional_recovery_speed"], weight:88, type:"risk", text:"被误解时,你容易当场被点燃,事后不舒服感也会留得比较久。所以对你来说,冲突里的语气、解释和修复非常关键。" })
  if (high(b.coldness_sensitivity) && low(c.emotional_recovery_speed)) R({ keys:["coldness_sensitivity","emotional_recovery_speed"], weight:90, type:"risk", text:"关系里的小变化对你不是\"看见就算了\"。一旦你捕捉到对方变冷,这种感觉可能会在心里停留比较久。" })
  if (high(a.task_initiation) && high(a.decision_assertiveness)) R({ keys:["task_initiation","decision_assertiveness"], weight:88, type:"core", text:"当局面散掉,而你又有判断时,你会自然想把事情定下来。你不是只负责气氛的人,也会在需要时承担方向感。" })
  if (high(a.task_initiation) && high(r.commitment_caution)) R({ keys:["task_initiation","commitment_caution"], weight:84, type:"strength", text:"你能推进事情,但不太会乱承诺。这种组合会让你显得可靠:不是光有行动力,而是知道什么能接、什么不能接。" })
  if (warmth === "active_warmth" && support === "emotional_holding" && high(b.coldness_sensitivity)) R({ keys:["warmth_initiation","support_style","coldness_sensitivity"], weight:94, type:"core", text:"你在关系里很能感知情绪,也会主动释放关心。相应地,你也很容易感受到对方情绪和回应的变化。你不是玻璃心,而是关系雷达很灵。" })
  if (conn === "resonance_connection" && low(d.social_energy) && high(d.sharing_drive)) R({ keys:["connection_value","social_energy","sharing_drive"], weight:90, type:"core", text:"你不是对所有人都有表达欲,而是遇到同频对象时会突然变得很想分享。你的热情不是平均分配的,而是被共鸣激活的。" })
  if (conn === "mutual_understanding_connection" && high(r.commitment_caution) && high(r.notice_expectation)) R({ keys:["connection_value","commitment_caution","notice_expectation"], weight:86, type:"core", text:"你要的理解不只是情绪上的懂,也包括对边界、承诺和预期的尊重。你会觉得真正懂你的人,不会随便答应,也不会临时变动却不交代。" })

  return out
}

function pickBestCombos(combos: ComboRule[], n: number): ComboRule[] {
  const picked: ComboRule[] = []
  const used = new Set<string>()
  for (const c of combos) {
    const overlap = c.keys.filter(k => used.has(k)).length
    if (overlap >= 2 && picked.length >= 2) continue
    picked.push(c)
    c.keys.forEach(k => used.add(k))
    if (picked.length >= n) break
  }
  return picked
}

function buildStrongTitle(p: any, features: Feature[]): { title: string; reason: string } {
  const topKeys = new Set(features.slice(0, 7).map(x => x.key))
  const d = p.dialogue, b = p.boundary_and_closeness, c = p.conflict_repair, w = p.relationship_warmth, a = p.agency, r = p.reliability
  const conn = w.connection_value.code
  const candidates: { weight: number; title: string; reason: string }[] = []
  const add = (weight: number, title: string, reason: string, keys: string[] = []) => {
    candidates.push({ weight: weight + keys.filter(k => topKeys.has(k)).length * 16, title, reason })
  }
  add(40, "你像是一个「通过关系质量来决定开放程度的人」", "基础兜底")
  if (low(d.social_energy) && high(d.sharing_drive)) add(95, "你像是一个「社交续航有限,但表达火花很亮的人」", "低社交能量 + 高分享欲", ["social_energy","sharing_drive"])
  if (high(b.coldness_sensitivity) && high(b.closeness_density_pressure)) add(100, "你像是一个「需要稳定靠近,但不能被亲密淹没的人」", "高冷淡敏感 + 高亲密压力", ["coldness_sensitivity","closeness_density_pressure"])
  if (high(b.interruption_sensitivity) && high(b.arranged_decision_discomfort)) add(96, "你像是一个「可以亲近,但不能被越过边界的人」", "高打断敏感 + 高被安排不适", ["interruption_sensitivity","arranged_decision_discomfort"])
  if (low(d.social_energy) && high(d.disagreement_exploration)) add(94, "你像是一个「入口很窄,但一旦聊深就会醒过来的人」", "低社交能量 + 高观点探索", ["social_energy","disagreement_exploration"])
  if (high(c.misunderstanding_regulation) && low(c.emotional_recovery_speed)) add(92, "你像是一个「表面能稳住,心里会慢慢消化的人」", "高误解调节 + 低情绪恢复速度", ["misunderstanding_regulation","emotional_recovery_speed"])
  if (conn === "resonance_connection" && high(d.sharing_drive) && low(d.social_energy)) add(106, "你像是一个「不对所有人打开,但遇到同频会突然变亮的人」", "共鸣连接 + 高分享欲 + 低社交能量", ["connection_value","sharing_drive","social_energy"])
  if (conn === "companionship_connection" && high(b.coldness_sensitivity)) add(96, "你像是一个「不一定常表达需求,但很在意对方是否稳定在场的人」", "陪伴连接 + 高冷淡敏感", ["connection_value","coldness_sensitivity"])
  if (conn === "mutual_understanding_connection" && high(b.interruption_sensitivity)) add(96, "你像是一个「想被懂,但不想被过度进入的人」", "理解连接 + 高打断敏感", ["connection_value","interruption_sensitivity"])
  if (high(a.task_initiation) && high(r.commitment_caution)) add(88, "你像是一个「能把事情推起来,也不会随便许诺的人」", "高推进 + 高承诺谨慎", ["task_initiation","commitment_caution"])
  candidates.sort((x, y) => y.weight - x.weight)
  return { title: candidates[0].title, reason: candidates[0].reason }
}

function buildRelationshipAdvice(features: Feature[]): string {
  const labels = features.slice(0, 7).map(x => x.label)
  if (labels.includes("强节奏边界") || labels.includes("自主感强")) return "所以和你相处最重要的不是更热情,而是更尊重节奏:提前说、给选择、别默认你随时可用。"
  if (labels.includes("关系温差敏感") || labels.includes("重视提前说明")) return "你会很受关系信号影响。稳定、清楚、可预期的回应,会比短暂热情更让你安心。"
  if (labels.includes("低频社交") && labels.includes("高分享欲")) return "你适合那种不要求你持续在线、但能接住你表达火花的关系。"
  if (labels.includes("观点探索") || labels.includes("共鸣连接")) return "真正吸引你的不是单纯热闹,而是能不能聊到更深、更准、更同频的地方。"
  return "你适合的关系不是固定模板,而是能同时容纳你的连接需求和个人节奏。"
}

function portrait(p: any): ProfilePortrait {
  const features = strongestFeatures(p)
  const strongest = new Set(features.slice(0, 7).map(x => x.key))
  const sorted = addComboRules(p, strongest).sort((a, b) => b.weight - a.weight)
  const picked = pickBestCombos(sorted, 6)
  const usedKeys = new Set(picked.flatMap(c => c.keys || []))
  const extraFeatures = features.filter(f => !usedKeys.has(f.key)).slice(0, 3)
  const titleObj = buildStrongTitle(p, features)
  const opening = `这份画像里最突出的不是所有维度的平均值,而是这些强信号:${features.slice(0, 4).map(x => x.label).join("、")}。下面的解读会优先围绕这些特征展开。`
  const body = [opening, ...picked.map(x => x.text), ...extraFeatures.map(x => x.text), buildRelationshipAdvice(features)].filter(Boolean)
  return {
    title: titleObj.title,
    main_type: titleObj.title.replace("你像是一个「", "").replace("」", ""),
    title_reason: titleObj.reason,
    core_tension: picked.find(x => ["core","tension","hidden"].includes(x.type))?.text || features[0]?.text || "",
    tags: Array.from(new Set([
      ...features.slice(0, 6).map(x => x.label),
      ...picked.slice(0, 4).map(x => x.type === "tension" ? "内在张力明显" : x.type === "hidden" ? "外显和内在不完全一致" : x.type === "risk" ? "易消耗点明显" : "核心特征突出"),
    ])).slice(0, 10),
    body,
    debug: { strongest_features: features.slice(0, 8), picked_combos: picked, title_reason: titleObj.reason },
  }
}

// ========================================
// Build profile
// ========================================

export function buildProfile(args: {
  answers: Record<string, number>
  domains: { interested: string[]; avoided: string[] }
}): Profile {
  const { answers: ans, domains } = args
  const p: any = {
    meta: { version: "agent-social-portrait-17q-strong-combo", generated_at: new Date().toISOString() },
    domains,
    raw_answers: Object.fromEntries(Q.map(q => [q.id, { option_index: ans[q.id] !== undefined ? ans[q.id] + 1 : null, option_text: txt(ans, q.id) }])),
    dialogue: { social_energy: val(ans, "E1"), sharing_drive: val(ans, "E3"), disagreement_exploration: val(ans, "O3") },
    relationship_warmth: { warmth_initiation: { ...tg(ans, "CMM1"), score: val(ans, "CMM1") }, support_style: tg(ans, "CMM2"), connection_value: tg(ans, "CMM3") },
    boundary_and_closeness: { interruption_sensitivity: val(ans, "AU2"), arranged_decision_discomfort: val(ans, "AU1"), closeness_density_pressure: val(ans, "AV3"), coldness_sensitivity: val(ans, "AX2") },
    reliability: { commitment_caution: val(ans, "CON4"), notice_expectation: val(ans, "CON2") },
    conflict_repair: { misunderstanding_regulation: val(ans, "ES3"), emotional_recovery_speed: val(ans, "ES2") },
    exploration: { novelty_seeking: val(ans, "O4") },
    agency: { task_initiation: val(ans, "D1"), decision_assertiveness: val(ans, "D2") },
  }
  p.portrait = portrait(p)
  return p as Profile
}
