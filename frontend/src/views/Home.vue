<template>
  <main class="commerce-shell">
    <section class="hero-panel">
      <nav class="topbar">
        <div class="brand">
          <span class="brand-mark">AG</span>
          <div>
            <strong>AssistGen</strong>
            <small>智能电商客服中枢</small>
          </div>
        </div>
        <div class="nav-tags">
          <span>Hybrid RAG</span>
          <span>Knowledge Graph</span>
          <span>Multi-Agent</span>
        </div>
      </nav>

      <div class="hero-grid">
        <section class="hero-copy">
          <p class="eyebrow">AI Shopping Concierge</p>
          <h1>不只是回答问题，而是把用户带到更好的购买决策。</h1>
          <p class="hero-desc">
            AssistGen 把商品检索、图关系推荐、GraphRAG 解释和答案质检拆成可协作的 Agent。
            它更像一个懂商品、懂搭配、也懂销售节奏的智能导购。
          </p>

          <div class="hero-actions">
            <button class="primary-btn" @click="focusChat">开始体验</button>
            <button class="secondary-btn" @click="fillPrompt('帮我给爸妈配一套 1500 元以内的家庭安防方案')">
              试试家庭安防方案
            </button>
          </div>

          <div class="metric-strip">
            <div>
              <strong>5</strong>
              <span>核心 Agent</span>
            </div>
            <div>
              <strong>2</strong>
              <span>检索通道</span>
            </div>
            <div>
              <strong>KG</strong>
              <span>搭配推荐</span>
            </div>
          </div>
        </section>

        <section class="console-card">
          <div class="console-head">
            <span>Agent Runtime</span>
            <b>Demo Mode</b>
          </div>

          <div class="agent-flow">
            <article v-for="agent in agents" :key="agent.name" class="flow-card">
              <span>{{ agent.step }}</span>
              <div>
                <strong>{{ agent.name }}</strong>
                <p>{{ agent.desc }}</p>
              </div>
            </article>
          </div>
        </section>
      </div>
    </section>

    <section class="workbench">
      <aside class="insight-panel">
        <div class="thinking-panel">
          <div class="thinking-head">
            <small>Agent 思考过程</small>
            <span class="thinking-status">{{ hasRunningStage ? '思考中...' : (hasStages ? '已完成' : '等待请求') }}</span>
          </div>
          <div class="stage-list">
            <div
              v-for="stage in agentStages"
              :key="stage.name"
              :class="['stage-row', stage.status]"
            >
              <span class="stage-dot" :class="stage.status"></span>
              <div class="stage-info">
                <strong>{{ stage.name }}</strong>
                <p>{{ stage.description }}</p>
              </div>
              <span v-if="stage.duration_ms" class="stage-time">{{ stage.duration_ms }}ms</span>
            </div>
          </div>
        </div>

        <div v-if="products.length" class="product-stack">
          <article v-for="product in products" :key="product.name" class="product-card">
            <div class="product-avatar">{{ product.short }}</div>
            <div>
              <div class="product-line">
                <h3>{{ product.name }}</h3>
                <b>¥{{ product.price }}</b>
              </div>
              <p>{{ product.reason }}</p>
              <span>{{ product.tag }}</span>
            </div>
          </article>
        </div>
      </aside>

      <section class="chat-panel">
        <header class="chat-header">
          <div>
            <small>Recommendation Agent</small>
            <h2>导购对话</h2>
          </div>
          <span class="live-badge">{{ connectionLabel }}</span>
          <button class="new-chat-btn" @click="onNewChat" title="新建聊天">＋</button>
        </header>

        <div v-if="memoryHint" class="memory-hint">{{ memoryHint }}</div>

        <div ref="chatBodyRef" class="chat-body">
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['message-row', message.role]"
          >
            <div class="avatar">{{ message.role === 'assistant' ? 'AG' : '你' }}</div>
            <div class="bubble">
              <div class="message-content" v-html="formatMessage(message.content)"></div>
              <div v-if="message.recommendations?.length" class="mini-products">
                <button
                  v-for="item in message.recommendations"
                  :key="item"
                  type="button"
                  @click="fillPrompt(`为什么推荐 ${item}？`)"
                >
                  {{ item }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="quick-prompts">
          <button v-for="prompt in prompts" :key="prompt" type="button" @click="fillPrompt(prompt)">
            {{ prompt }}
          </button>
        </div>

        <form class="chat-input" @submit.prevent="sendMessage">
          <input
            ref="inputRef"
            v-model="input"
            placeholder="输入购买需求，比如：我想买智能门锁和摄像头"
          />
          <button type="submit" :disabled="!input.trim() || isSending">
            {{ isSending ? '生成中' : '发送' }}
          </button>
        </form>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'

type ChatMessage = {
  id: number
  role: 'assistant' | 'user'
  content: string
  recommendations?: string[]
}

type AgentRecommendation = {
  product_id?: string
  product_name?: string
  category?: string
  price?: number
  stock?: number
  relation?: string
  reason?: string
  final_score?: number
}

type AgentTraceStep = {
  name: string
  status?: string
  summary: string
}

type AgentResponse = {
  answer: string
  recommendations: AgentRecommendation[]
  retrieval_candidates: AgentRecommendation[]
  agent_trace: AgentTraceStep[]
  metadata: Record<string, unknown>
}

const input = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const chatBodyRef = ref<HTMLElement | null>(null)
// latestTrace removed — left insight-panel is now the single source for agent progress
const memoryHint = ref('')
const isSending = ref(false)
const connectionLabel = ref('后端待连接')

// ── V3 session id ──────────────────────────────────────────────────
const SESSION_KEY = 'assistgen_session_id'

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = 'chat_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8)
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function newChatSession() {
  localStorage.removeItem(SESSION_KEY)
  getSessionId()
}

function onNewChat() {
  newChatSession()
  messages.value = []
  products.value = []
  latestTrace.value = []
  agentStages.value.forEach(s => { s.status = 'idle'; s.duration_ms = undefined })
  memoryHint.value = ''
}

// ── Agent Thinking Panel ─────────────────────────────────────────
type StageStatus = 'idle' | 'running' | 'done' | 'skipped' | 'error'
interface AgentStage {
  name: string
  description: string
  status: StageStatus
  duration_ms?: number
}

const STAGE_ORDER = ['Memory', 'Supervisor', 'Retrieval', 'Recommendation', 'Explanation', 'Critic']
// Final is intentionally hidden — the chat bubble is the final answer UI.
// If SSE emits Final running (e.g. tone rewrite), it still appears in trace strip.

const STAGE_DESCRIPTIONS: Record<string, string> = {
  Memory: '正在整理本轮上下文和购物偏好',
  Supervisor: '正在判断用户意图、预算和是否需要推荐',
  Retrieval: '正在从商品库、BM25 和向量检索中查找相关商品',
  Recommendation: '正在根据商品关系图生成搭配或加购推荐',
  Explanation: '正在结合商品关系和特点整理推荐理由',
  Critic: '正在检查预算约束、事实一致性和回答质量',
  Final: '正在生成最终导购回复'
}

const agentStages = ref<AgentStage[]>(
  STAGE_ORDER.map(name => ({ name, description: STAGE_DESCRIPTIONS[name] || '', status: 'idle' }))
)

const hasRunningStage = computed(() => agentStages.value.some(s => s.status === 'running'))
const hasStages = computed(() => agentStages.value.some(s => s.status !== 'idle'))

function resetStages() {
  agentStages.value = STAGE_ORDER.map(name => ({ name, description: STAGE_DESCRIPTIONS[name] || '', status: 'idle' }))
}

function updateStage(name: string, patch: Partial<AgentStage>) {
  const stage = agentStages.value.find(s => s.name === name)
  if (stage) Object.assign(stage, patch)
}
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8010').replace(/\/$/, '')

const agents = [
  { step: '01', name: 'Supervisor', desc: '判断意图、情绪、是否需要推荐或追问。' },
  { step: '02', name: 'Retrieval', desc: '用 Qdrant 向量检索和 BM25 找商品事实。' },
  { step: '03', name: 'Recommendation', desc: '根据商品关系生成搭配、加购和成套方案。' },
  { step: '04', name: 'Explanation', desc: '用 GraphRAG 组织为什么这样推荐。' },
  { step: '05', name: 'Critic', desc: '检查回答是否准确、完整、有销售帮助。' }
]

const products = ref([
  {
    short: '锁',
    name: '华为智选智能门锁 SE',
    price: 999,
    tag: '入口安全',
    reason: '适合作为家庭安防的主入口，能自然带出摄像头和传感器。'
  },
  {
    short: '摄',
    name: '小米智能摄像机 3 Pro',
    price: 299,
    tag: '远程看护',
    reason: '和门锁形成互补，解决开门记录之外的实时查看问题。'
  },
  {
    short: '感',
    name: 'Aqara 人体传感器 P1',
    price: 129,
    tag: '联动补强',
    reason: '补齐夜间移动感知，适合解释为低成本加购项。'
  }
])

const prompts = [
  '我想买智能门锁和摄像头',
  '帮我给爸妈配一套家庭安防',
  '为什么推荐这个组合？',
  '帮我配一套完整方案'
]

const messages = ref<ChatMessage[]>([
  {
    id: 1,
    role: 'assistant',
    content:
      '你好，我是 AssistGen。你可以告诉我预算、使用场景或已有设备，我会先查商品事实，再给出搭配推荐和解释。',
    recommendations: ['智能门锁', '摄像头', '人体传感器']
  }
])

const activeScenario = computed(() => {
  const lastUserMessage = [...messages.value].reverse().find((item) => item.role === 'user')?.content || ''

  if (lastUserMessage.includes('爸妈') || lastUserMessage.includes('安防')) {
    return {
      title: '家庭安防组合',
      desc: '优先推荐门锁、摄像头、人体传感器，控制预算和安装复杂度，适合从单品升级为方案。',
      score: '91'
    }
  }

  if (lastUserMessage.includes('为什么')) {
    return {
      title: '推荐解释模式',
      desc: '重点解释商品之间的互补关系，而不是只复述参数。用户追问时再触发更深的 GraphRAG 解释。',
      score: '86'
    }
  }

  if (lastUserMessage.includes('完整方案') || lastUserMessage.includes('配一套')) {
    return {
      title: '成套方案生成',
      desc: '从预算、场景、主商品和加购商品四个角度组织答案，让客服回复更像导购。',
      score: '94'
    }
  }

  return {
    title: '商品事实 + 搭配推荐',
    desc: '先检索价格、类别、卖点，再用知识图谱关系补充“还可以买什么”和“为什么”。',
    score: '89'
  }
})

function focusChat() {
  inputRef.value?.focus()
}

function fillPrompt(prompt: string) {
  input.value = prompt
  focusChat()
}

async function sendMessage() {
  const content = input.value.trim()
  if (!content || isSending.value) return

  isSending.value = true
  resetStages()
  messages.value.push({ id: Date.now(), role: 'user', content })
  input.value = ''
  await scrollToBottom()

  const thinkingId = Date.now() + 1
  messages.value.push({
    id: thinkingId,
    role: 'assistant',
    content: '正在调用后端 Agent：检索商品、计算推荐、生成解释...'
  })
  await scrollToBottom()

  try {
    const history = messages.value.filter((message) => message.id !== thinkingId)
    const result = await askAgentStream(content, history, thinkingId)
    connectionLabel.value = '后端已接入'

    const mc = (result.metadata?.memory_context || {}) as Record<string, unknown>
    memoryHint.value = (mc.hint_text as string) || ''

    replaceMessage(thinkingId, {
      id: thinkingId,
      role: 'assistant',
      content: result.answer || buildReply(content),
      recommendations: recommendationNames(result)
    })
    syncProducts(result)
  } catch (error) {
    connectionLabel.value = '后端离线，前端兜底'
    memoryHint.value = ''
    agentStages.value.forEach(s => { if (s.status === 'running') s.status = 'error' })
    replaceMessage(thinkingId, {
      id: thinkingId,
      role: 'assistant',
      content: `后端暂时没连上，我先用前端演示逻辑回答：${buildReply(content)}`,
      recommendations: pickRecommendations(content)
    })
  }

  isSending.value = false
  await scrollToBottom()
}

async function askAgent(content: string, history: ChatMessage[] = messages.value): Promise<AgentResponse> {
  const response = await fetch(`${apiBaseUrl}/api/agent/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: content,
      user_id: Number(localStorage.getItem('user_id') || 1),
      conversation_id: localStorage.getItem('conversation_id'),
      session_id: getSessionId(),
      messages: history.map((message) => ({
        role: message.role === 'assistant' ? 'assistant' : 'user',
        content: message.content
      }))
    })
  })

  if (!response.ok) {
    throw new Error(`Agent API failed: ${response.status}`)
  }

  return response.json()
}

async function askAgentStream(content: string, history: ChatMessage[], thinkingId: number): Promise<AgentResponse> {
  const payload = {
    query: content,
    user_id: Number(localStorage.getItem('user_id') || 1),
    conversation_id: localStorage.getItem('conversation_id'),
    session_id: getSessionId(),
    messages: history.map((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: message.content
    }))
  }

  try {
    const response = await fetch(`${apiBaseUrl}/api/agent/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!response.ok || !response.body) {
      throw new Error(`Stream failed: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResult: AgentResponse | null = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          if (event.type === 'stage') {
            // Update Agent Thinking Panel
            if (event.status === 'running') {
              updateStage(event.stage, { status: 'running' })
            } else if (event.status === 'compressing') {
              updateStage(event.stage, { status: 'running', description: event.message || '正在整理上下文...' })
            } else if (event.status === 'compressed') {
              updateStage(event.stage, { status: 'done', description: '上下文已整理', duration_ms: event.duration_ms })
            } else if (event.status === 'done') {
              updateStage(event.stage, { status: 'done', duration_ms: event.duration_ms })
            }
          } else if (event.type === 'final') {
            finalResult = event as unknown as AgentResponse
          }
          // error events are silently ignored; caller will fallback
        } catch { /* skip malformed SSE lines */ }
      }
    }

    if (finalResult) return finalResult
    throw new Error('No final event received')
  } catch {
    // Fallback to non-streaming endpoint
    return askAgent(content, history)
  }
}

function replaceMessage(id: number, message: ChatMessage) {
  const index = messages.value.findIndex((item) => item.id === id)
  if (index >= 0) {
    messages.value[index] = message
  } else {
    messages.value.push(message)
  }
}

function recommendationNames(result: AgentResponse) {
  const names = result.recommendations
    ?.map((item) => item.product_name)
    .filter((name): name is string => Boolean(name))
    .slice(0, 4)

  return names?.length ? names : undefined
}

function syncProducts(result: AgentResponse) {
  if (!result.recommendations?.length) return
  products.value = result.recommendations.slice(0, 3).map((item, index) => ({
    short: item.category?.slice(2, 3) || String(index + 1),
    name: item.product_name || '推荐商品',
    price: Number(item.price || 0),
    tag: item.relation || item.category || '推荐',
    reason: item.reason || '后端 Agent 根据商品关系和当前需求给出的推荐。'
  }))
}

function simulateMessage(content: string) {
  window.setTimeout(async () => {
    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: buildReply(content),
      recommendations: pickRecommendations(content)
    })
    await scrollToBottom()
  }, 360)
}

function buildReply(content: string) {
  if (content.includes('为什么')) {
    return '推荐逻辑是：门锁负责入口安全，摄像头负责远程查看，人体传感器负责异常感知。它们不是同类替代，而是互补关系，所以更适合组成家庭安防方案。'
  }

  if (content.includes('爸妈') || content.includes('安防')) {
    return '我会优先控制预算和安装复杂度。建议用智能门锁 + 室内摄像头 + 人体传感器做基础安防，价格更可控，也方便老人使用。'
  }

  if (content.includes('完整方案') || content.includes('配一套')) {
    return '完整方案可以分三层：入口用智能门锁，客厅或玄关放摄像头，夜间用人体传感器做联动提醒。如果预算允许，再补一个智能灯具做自动照明。'
  }

  if (content.includes('门锁') || content.includes('摄像头')) {
    return '已匹配到门锁和摄像头需求。门锁建议选华为智选智能门锁 SE，摄像头建议选小米智能摄像机 3 Pro；如果想成套使用，可以再补一个人体传感器。'
  }

  return '我可以按预算、房型、安装难度和已有设备帮你配套。你可以继续告诉我：预算多少、给谁用、主要想解决什么问题。'
}

function pickRecommendations(content: string) {
  if (content.includes('为什么')) return ['门锁 + 摄像头', '传感器联动']
  if (content.includes('安防') || content.includes('门锁') || content.includes('完整方案')) {
    return ['华为智选智能门锁 SE', '小米智能摄像机 3 Pro', 'Aqara 人体传感器 P1']
  }
  return ['智能门锁', '智能摄像头', '智能灯具']
}

function formatMessage(content: string) {
  return escapeHtml(content || '')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

async function scrollToBottom() {
  await nextTick()
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
  }
}
</script>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  background:
    radial-gradient(circle at 12% 12%, rgba(234, 112, 57, 0.2), transparent 30rem),
    radial-gradient(circle at 88% 18%, rgba(44, 88, 68, 0.2), transparent 28rem),
    linear-gradient(135deg, #f7efe3 0%, #efe0c7 46%, #d9e5d8 100%);
  color: #24170d;
}

button,
input {
  font: inherit;
}

button {
  border: 0;
  cursor: pointer;
}

.commerce-shell {
  min-height: 100vh;
  padding: 22px;
  font-family: "HarmonyOS Sans SC", "Alibaba PuHuiTi", "Microsoft YaHei", sans-serif;
}

.hero-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(50, 37, 23, 0.12);
  border-radius: 36px;
  background:
    linear-gradient(120deg, rgba(255, 252, 244, 0.92), rgba(250, 226, 185, 0.72)),
    repeating-linear-gradient(90deg, rgba(34, 47, 37, 0.045) 0 1px, transparent 1px 78px);
  box-shadow: 0 26px 90px rgba(64, 48, 28, 0.18);
}

.hero-panel::before,
.hero-panel::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
}

.hero-panel::before {
  width: 360px;
  height: 360px;
  right: -90px;
  top: -150px;
  background: rgba(231, 95, 45, 0.16);
}

.hero-panel::after {
  width: 260px;
  height: 260px;
  left: 46%;
  bottom: -150px;
  background: rgba(31, 51, 41, 0.14);
}

.topbar,
.hero-grid,
.workbench {
  max-width: 1340px;
  margin: 0 auto;
}

.topbar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 28px 0;
}

.brand,
.nav-tags,
.hero-actions,
.metric-strip,
.product-line,
.chat-header,
.quick-prompts,
.mini-products {
  display: flex;
  align-items: center;
}

.brand {
  gap: 12px;
}

.brand-mark {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 18px;
  background: #1f3329;
  color: #f6c76f;
  font-weight: 900;
  letter-spacing: -0.08em;
}

.brand strong,
.brand small {
  display: block;
}

.brand strong {
  font-size: 18px;
}

.brand small,
.eyebrow,
.panel-title small,
.chat-header small,
.score-card small,
.console-head {
  color: #765c3f;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.nav-tags {
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.nav-tags span,
.new-chat-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(31, 51, 41, 0.12);
  background: rgba(255, 255, 255, 0.7);
  color: #1f3329;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.new-chat-btn:hover {
  background: rgba(231, 95, 45, 0.08);
  border-color: #e75f2d;
  color: #e75f2d;
}

.live-badge {
  border: 1px solid rgba(31, 51, 41, 0.15);
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.56);
  color: #4a3825;
  font-size: 13px;
}

.hero-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
  gap: 36px;
  padding: 74px 28px 46px;
}

.hero-copy h1 {
  max-width: 860px;
  margin: 12px 0 18px;
  font-size: clamp(42px, 5.9vw, 82px);
  line-height: 0.98;
  letter-spacing: -0.07em;
}

.hero-desc {
  max-width: 720px;
  color: #604b32;
  font-size: 18px;
  line-height: 1.85;
}

.hero-actions {
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 34px;
}

.primary-btn,
.secondary-btn,
.chat-input button {
  border-radius: 999px;
  padding: 13px 20px;
  font-weight: 800;
}

.primary-btn,
.chat-input button {
  background: #e75f2d;
  color: #fff8ec;
  box-shadow: 0 14px 30px rgba(231, 95, 45, 0.28);
}

.secondary-btn {
  border: 1px solid rgba(31, 51, 41, 0.18);
  background: rgba(255, 255, 255, 0.62);
  color: #1f3329;
}

.metric-strip {
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 44px;
}

.metric-strip div {
  min-width: 116px;
  border-left: 2px solid rgba(231, 95, 45, 0.48);
  padding-left: 14px;
}

.metric-strip strong {
  display: block;
  font-size: 33px;
  letter-spacing: -0.05em;
}

.metric-strip span {
  color: #735b3c;
}

.console-card,
.insight-panel,
.chat-panel {
  border: 1px solid rgba(31, 51, 41, 0.13);
  border-radius: 30px;
  background: rgba(255, 252, 244, 0.76);
  box-shadow: 0 18px 62px rgba(54, 43, 26, 0.13);
  backdrop-filter: blur(18px);
}

.console-card {
  padding: 22px;
}

.console-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}

.console-head b {
  color: #e75f2d;
}

.agent-flow {
  display: grid;
  gap: 12px;
}

.flow-card {
  display: grid;
  grid-template-columns: 50px 1fr;
  gap: 14px;
  align-items: start;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.6);
  padding: 15px;
  animation: rise 0.7s ease both;
}

.flow-card span {
  color: #e75f2d;
  font-weight: 900;
}

.flow-card strong {
  display: block;
  margin-bottom: 4px;
}

.flow-card p,
.panel-title p,
.product-card p,
.message-content {
  margin: 0;
  color: #6c563a;
  line-height: 1.65;
}

.workbench {
  display: grid;
  grid-template-columns: 420px minmax(0, 1fr);
  gap: 22px;
  padding-top: 22px;
}

.insight-panel,
.chat-panel {
  padding: 22px;
}

.panel-title h2 {
  margin: 7px 0 9px;
  font-size: 28px;
}

.thinking-panel {
  margin-bottom: 18px;
}

.thinking-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.thinking-head small {
  color: #765c3f;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.thinking-status {
  color: #e75f2d;
  font-size: 11px;
  font-weight: 700;
}

.stage-list {
  display: grid;
  gap: 6px;
}

.stage-row {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 14px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.54);
  transition: background 0.3s, box-shadow 0.3s;
}

.stage-row.idle {
  opacity: 0.5;
}

.stage-row.done {
  opacity: 0.82;
}

.stage-row.error {
  background: rgba(231, 95, 45, 0.08);
}

.stage-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  background: rgba(31, 51, 41, 0.2);
  transition: background 0.3s, box-shadow 0.3s;
}

.stage-dot.done {
  background: #1f3329;
}

.stage-dot.running {
  background: #e75f2d;
  box-shadow: 0 0 0 4px rgba(231, 95, 45, 0.28);
  animation: pulse-dot 0.9s ease-in-out infinite;
}

.stage-dot.error {
  background: #e75f2d;
  box-shadow: 0 0 0 3px rgba(231, 95, 45, 0.18);
}

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 0 3px rgba(231, 95, 45, 0.3); }
  50% { box-shadow: 0 0 0 8px rgba(231, 95, 45, 0.08); }
}

.stage-row.running {
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 0 0 1px rgba(231, 95, 45, 0.12);
}

.stage-info {
  flex: 1;
  min-width: 0;
}

.stage-info strong {
  display: block;
  font-size: 13px;
  color: #1f3329;
  margin-bottom: 2px;
}

.stage-info p {
  margin: 0;
  font-size: 11px;
  color: #765c3f;
  line-height: 1.4;
}

.stage-row.running .stage-info strong {
  color: #e75f2d;
}

.stage-time {
  font-size: 10px;
  color: #9e8a6f;
  white-space: nowrap;
  font-weight: 600;
}

.score-card {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 16px;
  margin: 18px 0;
  border-radius: 26px;
  padding: 18px;
  background: #1f3329;
  color: #fff8ec;
}

.score-card strong {
  display: block;
  margin-top: 6px;
  font-size: 48px;
  line-height: 1;
}

.score-card small {
  color: rgba(255, 248, 236, 0.68);
}

.score-bars {
  display: grid;
  gap: 10px;
}

.score-bars span {
  position: relative;
  overflow: hidden;
  border-radius: 999px;
  padding: 8px 11px;
  background: rgba(255, 248, 236, 0.11);
  color: rgba(255, 248, 236, 0.82);
  font-size: 12px;
}

.score-bars span::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--w);
  background: rgba(246, 199, 111, 0.22);
}

.product-stack {
  display: grid;
  gap: 12px;
}

.product-card {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 14px;
  border-radius: 24px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.64);
}

.product-avatar {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  border-radius: 20px;
  background: #f6c76f;
  color: #2b1a0d;
  font-weight: 900;
}

.product-line {
  justify-content: space-between;
  gap: 12px;
}

.product-line h3 {
  margin: 0 0 5px;
  font-size: 16px;
}

.product-line b {
  color: #e75f2d;
  white-space: nowrap;
}

.product-card span {
  display: inline-block;
  margin-top: 10px;
  border-radius: 999px;
  background: rgba(31, 51, 41, 0.08);
  padding: 5px 9px;
  color: #2d3e32;
  font-size: 12px;
  font-weight: 800;
}

.chat-panel {
  height: min(760px, calc(100vh - 46px));
  min-height: 620px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto auto auto;
  overflow: hidden;
}

.chat-header {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.chat-header h2 {
  margin: 4px 0 0;
  font-size: 31px;
}

.memory-hint {
  margin: 0 0 12px;
  border-radius: 16px;
  background: rgba(31, 51, 41, 0.06);
  padding: 10px 16px;
  color: #5a4328;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
}

.chat-body {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  border-radius: 26px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.48), rgba(255, 255, 255, 0.48)),
    radial-gradient(circle at 18% 20%, rgba(246, 199, 111, 0.32), transparent 22rem);
  padding: 18px;
  scrollbar-color: rgba(31, 51, 41, 0.26) transparent;
  scrollbar-width: thin;
}

.chat-body::-webkit-scrollbar {
  width: 8px;
}

.chat-body::-webkit-scrollbar-track {
  background: transparent;
}

.chat-body::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(31, 51, 41, 0.24);
}

.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar {
  display: grid;
  flex: 0 0 auto;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 16px;
  background: #1f3329;
  color: #f6c76f;
  font-size: 13px;
  font-weight: 900;
}

.message-row.user .avatar {
  background: #e75f2d;
  color: #fff8ec;
}

.bubble {
  max-width: min(720px, 78%);
  border-radius: 23px;
  padding: 15px 16px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 10px 28px rgba(54, 43, 26, 0.08);
}

.message-row.user .bubble {
  background: #1f3329;
}

.message-row.user .message-content {
  color: #fff8ec;
}

.message-content {
  white-space: normal;
}

.message-content :deep(strong) {
  display: inline-block;
  margin: 6px 0 2px;
  color: #24170d;
}

.message-row.user .message-content :deep(strong) {
  color: #fff8ec;
}

.mini-products,
.quick-prompts {
  gap: 8px;
  flex-wrap: wrap;
}

.mini-products {
  margin-top: 12px;
}

.mini-products button,
.quick-prompts button {
  border-radius: 999px;
  background: #f6c76f;
  color: #3b2a16;
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 800;
}

.quick-prompts {
  margin: 16px 0 12px;
}

.quick-prompts button {
  background: rgba(31, 51, 41, 0.08);
}

.chat-input {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  border-radius: 25px;
  background: rgba(255, 255, 255, 0.8);
  padding: 10px;
}

.chat-input input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  padding: 0 12px;
  color: #24170d;
}

.chat-input button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 980px) {
  .commerce-shell {
    padding: 12px;
  }

  .topbar,
  .hero-grid {
    padding-left: 18px;
    padding-right: 18px;
  }

  .topbar,
  .hero-actions,
  .metric-strip {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-grid,
  .workbench {
    grid-template-columns: 1fr;
  }

  .hero-copy h1 {
    font-size: clamp(38px, 12vw, 58px);
  }

  .score-card {
    grid-template-columns: 1fr;
  }

  .chat-panel {
    height: min(700px, calc(100vh - 24px));
    min-height: 560px;
  }

  .bubble {
    max-width: 86%;
  }
}
</style>
