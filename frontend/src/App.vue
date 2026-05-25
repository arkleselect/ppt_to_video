<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Check, ChevronDown, CircleHelp, Download, FileUp, LoaderCircle, Square } from 'lucide-vue-next'

const fileName = ref('还没有文件')
const selectedFile = ref(null)
const fileInput = ref(null)
const uploadId = ref('')
const selectedVoice = ref('')
const selectedRate = ref('-5%')
const useTargetDuration = ref(false)
const targetMinutes = ref(40)
const voiceOpen = ref(false)
const rateOpen = ref(false)
const batchFileInput = ref(null)
const batchItems = ref([])
const batchVoiceOpen = ref(false)
const batchRateOpen = ref(false)
const batchMode = ref('video')
const batchUseTargetDuration = ref(false)
const batchTargetMinutes = ref(40)
const batchExpandedId = ref('')
const isBatchStarting = ref(false)
const batchAutoRun = ref(false)
const batchConcurrency = ref('3')
const batchAutoRetry = ref(true)
const batchMaxAutoRetries = 2
const isDragging = ref(false)
const isAnalyzing = ref(false)
const isPreviewing = ref(false)
const isGenerating = ref(false)
const analysis = ref(null)
const estimatedMinutes = ref(null)
const jobId = ref('')
const jobStatus = ref('')
const lastPolledStatus = ref('')
const downloadUrl = ref('')
const audioUrl = ref('')
const analyzeController = ref(null)
const serverLogs = ref([])
const tokenUsage = ref({
  model: '',
  pricing: {
    input_per_million: 2.5,
    completion_per_million: 15,
    cache_read_per_million: 0.25,
  },
  totals: {
    input_tokens: 0,
    completion_tokens: 0,
    cache_read_tokens: 0,
    total_tokens: 0,
    input_cost: 0,
    completion_cost: 0,
    cache_read_cost: 0,
    total_cost: 0,
  },
  history: [],
})
const activeTab = ref(localStorage.getItem('activeTab') || 'single')
const settings = ref({
  ai_base_url: '',
  ai_api_key: '',
  ai_model: '',
  ai_verify_ssl: true,
  default_script_style: '培训讲师 · 稳妥清晰',
  subtitle_style: 'classic',
  has_api_key: false,
})
const settingsMessage = ref('')
const isSavingSettings = ref(false)
const subtitleSettingsMessage = ref('')
const isSavingSubtitleSettings = ref(false)
const isTestingAI = ref(false)
const autoExpandDuration = ref(true)
const scriptFile = ref(null)
const scriptFileName = ref('还没有文件')
const scriptFileInput = ref(null)
const scriptUploadId = ref('')
const scriptSlides = ref([])
const generatedScripts = ref([])
const scriptLogs = ref([])
const scriptStrategy = ref('short')
const scriptStyle = ref('培训讲师 · 稳妥清晰')
const scriptEnrichment = ref('light')
const batchEnrichmentOpen = ref(false)
const enrichmentOpen = ref(false)
const activeStrategyPopover = ref('')
const shortNoteThreshold = ref(180)
const scriptTargetMinutes = ref(40)
const batchScriptStrategy = ref('short')
const batchScriptStyle = ref('培训讲师 · 稳妥清晰')
const batchScriptEnrichment = ref('light')
const batchShortNoteThreshold = ref(180)
const batchScriptTargetMinutes = ref(40)
const batchScriptAutoPageMultiplier = ref(2)
const batchAutoExpandDuration = ref(true)
const isScriptAnalyzing = ref(false)
const isScriptGenerating = ref(false)
const scriptJobId = ref('')
const scriptJobStatus = ref('')
const scriptAnalyzeMessage = ref('')
const scriptGenerateMessage = ref('')
const scriptPptDownloadUrl = ref('')

const voices = ref([])
const rates = [
  { label: '偏慢', value: '-15%' },
  { label: '自然偏稳', value: '-5%' },
  { label: '标准', value: '+0%' },
  { label: '偏快', value: '+10%' },
]
const enrichmentOptions = [
  { label: '严格基于原文', value: 'strict', hint: '只整理页面和原备注，不主动增加背景。' },
  { label: '少量背景解释', value: 'light', hint: '保留事实边界，补一点必要说明。' },
  { label: '教学化展开', value: 'teaching', hint: '增加讲解层次、原因和注意点。' },
  { label: '过渡串联', value: 'transition', hint: '强化上下文衔接，让口播更连贯。' },
]
const subtitleStyleOptions = [
  { label: '经典白字', value: 'classic', hint: '白字深描边，适合大多数培训课件。', sample: '这是当前页面的讲解字幕示例' },
  { label: '加粗强调', value: 'bold', hint: '更醒目，适合投影或复杂背景。', sample: '这是当前页面的讲解字幕示例' },
  { label: '轻量简洁', value: 'minimal', hint: '字号略小，画面遮挡更少。', sample: '这是当前页面的讲解字幕示例' },
]
const logs = ref([])
const batchPollers = new Map()
let settingsMessageTimer = null
let subtitleSettingsMessageTimer = null

const batchDownloadableItems = computed(() =>
  batchItems.value.filter((item) => item.output || item.pptOutput),
)
const batchConcurrencyLimit = computed(() =>
  Number(batchConcurrency.value) || 1,
)

function loadClientUser() {
  const storageKey = 'pptToVideoClientUser'
  const existing = localStorage.getItem(storageKey)
  if (existing) return existing
  const suffix = (window.crypto?.randomUUID?.() || `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`)
    .replace(/-/g, '')
    .slice(0, 6)
    .toUpperCase()
  const user = `用户-${suffix}`
  localStorage.setItem(storageKey, user)
  return user
}

const currentUser = ref(loadClientUser())

function userHeaders(extra = {}) {
  return {
    ...extra,
    'X-Client-User': encodeURIComponent(currentUser.value),
  }
}

function downloadLink(filename, downloadName = '') {
  if (!filename) return ''
  const query = downloadName ? `?name=${encodeURIComponent(downloadName)}` : ''
  return `/api/download/${encodeURIComponent(filename)}${query}`
}

function formatTokenCount(value) {
  const amount = Number(value || 0)
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(2)}M`
  if (amount >= 1_000) return `${(amount / 1_000).toFixed(1)}K`
  return `${Math.round(amount)}`
}

function formatUsd(value) {
  return `$${Number(value || 0).toFixed(4)}`
}

function chartPoints(values, width = 164, height = 42) {
  if (!values.length) {
    return `0,${height} ${width},${height}`
  }
  const maxValue = Math.max(...values, 1)
  if (values.length === 1) {
    const y = height - (values[0] / maxValue) * height
    return `0,${y.toFixed(1)} ${width},${y.toFixed(1)}`
  }
  return values.map((value, index) => {
    const x = (index / (values.length - 1)) * width
    const y = height - (value / maxValue) * height
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function historySeries(field) {
  return tokenUsage.value.history.map((item) => Number(item[field] || 0))
}

function logUser(text = '') {
  const match = text.match(/（(用户-[A-Za-z0-9_-]+)）/)
  return match?.[1] || ''
}

function logUserTone(user = '') {
  if (!user) return {}
  let hash = 0
  for (const char of user) {
    hash = (hash * 31 + char.charCodeAt(0)) % 360
  }
  const hues = [18, 42, 82, 148, 188, 218, 268, 318]
  const hue = hues[hash % hues.length]
  return {
    '--log-user-bg': `hsl(${hue} 34% 92%)`,
    '--log-user-border': `hsl(${hue} 24% 72%)`,
    '--log-user-text': `hsl(${hue} 28% 30%)`,
    '--log-user-accent': `hsl(${hue} 34% 48%)`,
  }
}

function loadTokenUsageIfNeeded() {
  if (activeTab.value === 'tokenUsage') {
    loadTokenUsage()
  }
}

async function loadTokenUsage() {
  try {
    tokenUsage.value = await fetch('/api/token-usage').then(readJson)
  } catch {
    tokenUsage.value = {
      ...tokenUsage.value,
      history: [],
    }
  }
}

async function readJson(response) {
  const text = await response.text()
  let data
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    throw new Error('接口没有返回 JSON，请确认前端通过 npm run dev 启动，并且后端服务正在运行。')
  }
  if (!response.ok) {
    throw new Error(data.error || data.message || `请求失败：HTTP ${response.status}`)
  }
  return data
}

function onFileChange(event) {
  setFile(event.target.files?.[0])
}

function setFile(file) {
  if (!file) return
  selectedFile.value = file
  fileName.value = file.name
  uploadId.value = ''
  analysis.value = null
  logs.value = []
  downloadUrl.value = ''
}

function clearFile() {
  selectedFile.value = null
  fileName.value = '还没有文件'
  uploadId.value = ''
  analysis.value = null
  estimatedMinutes.value = null
  downloadUrl.value = ''
  logs.value = []
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

function onDrop(event) {
  isDragging.value = false
  setFile(event.dataTransfer.files?.[0])
}

function addLog(text, state = '进行中') {
  logs.value.unshift({
    time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    text,
    state,
  })
}

function clearLogs() {
  logs.value = []
}

function makeBatchId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function createBatchItem(file) {
  return {
    id: makeBatchId(),
    file,
    name: file.name,
    uploadId: '',
    jobId: '',
    slides: null,
    chars: null,
    status: '待开始',
    statusTone: 'muted',
    latestLog: '等待上传',
    logs: [],
    output: '',
    outputDownloadName: '',
    pptOutput: '',
    pptDownloadName: '',
    estimatedMinutes: null,
    automatedTargetMinutes: null,
    resultKind: '',
    queuedStart: false,
    queuedRetry: false,
    autoRetryCount: 0,
    error: '',
  }
}

function addBatchFiles(fileList) {
  const files = Array.from(fileList || []).filter((file) => file.name.toLowerCase().endsWith('.pptx'))
  if (!files.length) return
  batchItems.value = [
    ...batchItems.value,
    ...files.map(createBatchItem),
  ]
}

function onBatchFilesChange(event) {
  addBatchFiles(event.target.files)
  if (batchFileInput.value) {
    batchFileInput.value.value = ''
  }
}

function onBatchDrop(event) {
  isDragging.value = false
  addBatchFiles(event.dataTransfer.files)
}

function removeBatchItem(itemId) {
  stopBatchPolling(itemId)
  const index = batchItems.value.findIndex((item) => item.id === itemId)
  if (index >= 0) {
    batchItems.value.splice(index, 1)
  }
  if (batchExpandedId.value === itemId) {
    batchExpandedId.value = ''
  }
}

function clearBatchQueue() {
  batchItems.value.forEach((item) => stopBatchPolling(item.id))
  batchItems.value = []
  batchExpandedId.value = ''
}

function pushBatchLog(item, text, state = '进行中') {
  item.logs = [
    {
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      text,
      state,
    },
    ...item.logs,
  ]
  item.latestLog = text
}

function batchStatusClass(item) {
  const failedStatuses = ['分析失败', '创建失败', '失败', '状态读取失败']
  const waitingStatuses = ['等待中', '排队中']
  const runningStatuses = ['分析中', '生成中']
  return {
    'queue-status': true,
    muted: item.statusTone === 'muted',
    running: runningStatuses.includes(item.status),
    waiting: waitingStatuses.includes(item.status),
    failed: failedStatuses.includes(item.status),
    done: item.statusTone === 'done',
  }
}

function isBatchRunnableStatus(status) {
  return ['待开始', '待生成', '分析失败', '创建失败', '失败', '已停止', '状态读取失败', '等待中'].includes(status)
}

function isBatchAutoRunnableStatus(status) {
  return ['待开始', '待生成', '等待中'].includes(status)
}

function runningBatchCount(exceptId = '') {
  return batchItems.value.filter((item) => item.id !== exceptId && item.statusTone === 'running').length
}

function hasBatchCapacity(exceptId = '') {
  return runningBatchCount(exceptId) < batchConcurrencyLimit.value
}

function automatedBatchTargetMinutes(item) {
  const slides = Number(item.slides) || 1
  const multiplier = Math.max(0.1, Number(batchScriptAutoPageMultiplier.value) || 2)
  return Math.max(1, Math.round(slides * multiplier))
}

async function maybeStartNextBatchItem() {
  const hasQueuedWaitingItem = batchItems.value.some((item) => item.queuedStart && item.status === '等待中')
  if (!batchAutoRun.value && !hasQueuedWaitingItem) return
  while (hasBatchCapacity()) {
    const nextItem = batchItems.value.find((item) =>
      (item.queuedStart && item.status === '等待中')
      || (batchAutoRun.value && isBatchAutoRunnableStatus(item.status)),
    )
    if (!nextItem) break
    if (nextItem.queuedRetry) {
      nextItem.queuedRetry = false
      await retryBatchScriptJob(nextItem)
      continue
    }
    await startBatchItem(nextItem, { force: true })
  }
  if (
    batchAutoRun.value
    && !batchItems.value.some((item) => isBatchAutoRunnableStatus(item.status) || item.statusTone === 'running')
  ) {
    batchAutoRun.value = false
  }
}

async function analyzeBatchItem(item) {
  if (item.uploadId) return true
  item.status = '分析中'
  item.statusTone = 'running'
  pushBatchLog(item, '正在上传并分析课件。')
  const formData = new FormData()
  formData.append('pptx', item.file)
  try {
    const endpoint = batchMode.value === 'script' ? '/api/script/analyze' : '/api/analyze'
    const data = await fetch(endpoint, {
      method: 'POST',
      headers: userHeaders(),
      body: formData,
    }).then(readJson)
    item.uploadId = data.upload_id
    item.slides = data.slide_count ?? data.slides
    item.chars = data.chars
    item.status = '待生成'
    item.statusTone = 'muted'
    pushBatchLog(item, `分析完成：共 ${item.slides} 页，备注约 ${data.chars} 字。`, '完成')
    return true
  } catch (error) {
    item.error = error.message || '分析失败'
    item.status = '分析失败'
    item.statusTone = 'muted'
    pushBatchLog(item, item.error, '失败')
    return false
  }
}

async function startBatchItem(item, options = {}) {
  const { force = false } = options
  if (item.statusTone === 'running') return false
  if (!force && !hasBatchCapacity(item.id)) {
    item.status = '等待中'
    item.statusTone = 'muted'
    item.queuedStart = true
    pushBatchLog(item, `当前并发上限为 ${batchConcurrency.value}，已加入等待队列，空位释放后会自动开始。`, '待处理')
    batchExpandedId.value = item.id
    return false
  }
  item.queuedStart = false
  item.queuedRetry = false
  item.error = ''
  item.output = ''
  item.outputDownloadName = ''
  item.pptOutput = ''
  item.pptDownloadName = ''
  item.automatedTargetMinutes = null
  item.resultKind = batchMode.value
  const ready = await analyzeBatchItem(item)
  if (!ready) {
    await maybeStartNextBatchItem()
    return false
  }
  const scriptTargetMinutes = batchScriptStrategy.value === 'auto'
    ? automatedBatchTargetMinutes(item)
    : Number(batchScriptTargetMinutes.value) || 40
  if (batchMode.value === 'script' && batchScriptStrategy.value === 'auto') {
    item.automatedTargetMinutes = scriptTargetMinutes
    pushBatchLog(item, `自动化策略：${item.slides || 0} 页 × ${Number(batchScriptAutoPageMultiplier.value) || 2} 倍，目标讲稿时长约 ${scriptTargetMinutes} 分钟。`)
  }
  item.status = '排队中'
  item.statusTone = 'running'
  pushBatchLog(item, batchMode.value === 'script' ? '已创建讲稿生成任务。' : '已创建视频生成任务。')
  try {
    const endpoint = batchMode.value === 'script' ? '/api/script/generate' : '/api/generate'
    const body = batchMode.value === 'script'
      ? {
          upload_id: item.uploadId,
          user_id: currentUser.value,
          strategy: batchScriptStrategy.value === 'auto' ? 'duration' : batchScriptStrategy.value,
          style: batchScriptStyle.value,
          enrichment: batchScriptEnrichment.value,
          short_threshold: Number(batchShortNoteThreshold.value) || 180,
          target_minutes: scriptTargetMinutes,
          automation: batchScriptStrategy.value === 'auto'
            ? {
                page_multiplier: Number(batchScriptAutoPageMultiplier.value) || 2,
                slide_count: Number(item.slides) || 0,
              }
            : null,
          auto_expand_duration: batchAutoExpandDuration.value,
        }
      : {
          upload_id: item.uploadId,
          user_id: currentUser.value,
          voice: selectedVoice.value,
          rate: selectedRate.value,
          subtitle_style: settings.value.subtitle_style,
          ...(batchUseTargetDuration.value ? { target_minutes: Number(batchTargetMinutes.value) || 40 } : {}),
        }
    const data = await fetch(endpoint, {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    }).then(readJson)
    item.jobId = data.job_id
    item.status = '生成中'
    item.statusTone = 'running'
    startBatchPolling(item)
    return true
  } catch (error) {
    item.error = error.message || '创建任务失败'
    item.status = '创建失败'
    item.statusTone = 'muted'
    pushBatchLog(item, item.error, '失败')
    await maybeStartNextBatchItem()
    return false
  }
}

function stopBatchPolling(itemId) {
  const timer = batchPollers.get(itemId)
  if (timer) {
    clearInterval(timer)
    batchPollers.delete(itemId)
  }
}

function startBatchPolling(item) {
  stopBatchPolling(item.id)
  const timer = setInterval(async () => {
    try {
      const data = await fetch(`/api/jobs/${item.jobId}`).then(readJson)
      if (data.logs?.length) {
        item.logs = [...data.logs].reverse()
        item.latestLog = data.logs[data.logs.length - 1]?.text || item.latestLog
      }
      if (data.status === 'queued' || data.status === 'running') {
        item.status = data.status === 'queued' ? '排队中' : '生成中'
        item.statusTone = 'running'
      }
      if (data.status === 'done') {
        stopBatchPolling(item.id)
        item.status = '已完成'
        item.statusTone = 'done'
        item.autoRetryCount = 0
        if (item.resultKind === 'script') {
          item.pptOutput = data.result?.ppt_output || ''
          item.pptDownloadName = data.result?.ppt_download_name || item.name
          item.estimatedMinutes = data.result?.estimated_minutes ?? null
          item.latestLog = data.result?.expansion_applied
            ? '讲稿生成完成，已自动补写一轮。'
            : '讲稿生成完成，可以下载 PPT。'
        } else {
          item.output = data.output
          item.outputDownloadName = data.output_download_name || item.name.replace(/\.pptx$/i, '.mp4')
          item.latestLog = '视频生成完成，可以下载。'
        }
        item.logs = [
          {
            time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
            text: item.latestLog,
            state: '完成',
          },
          ...item.logs,
        ]
        await maybeStartNextBatchItem()
      }
      if (data.status === 'error') {
        stopBatchPolling(item.id)
        item.status = '失败'
        item.statusTone = 'muted'
        item.error = data.logs?.[data.logs.length - 1]?.text || (item.resultKind === 'script' ? '讲稿生成失败' : '视频生成失败')
        item.latestLog = item.error
        batchExpandedId.value = item.id
        if (await maybeAutoRetryBatchItem(item, item.error)) return
        await maybeStartNextBatchItem()
      }
      if (data.status === 'stopped') {
        stopBatchPolling(item.id)
        item.status = '已停止'
        item.statusTone = 'muted'
        item.latestLog = '任务已停止。'
        await maybeStartNextBatchItem()
      }
    } catch (error) {
      stopBatchPolling(item.id)
      item.status = '状态读取失败'
      item.statusTone = 'muted'
      item.error = error.message || '读取任务状态失败'
      item.latestLog = item.error
      batchExpandedId.value = item.id
      await maybeStartNextBatchItem()
    }
  }, 2000)
  batchPollers.set(item.id, timer)
}

async function startAllBatchItems() {
  if (!batchItems.value.length || isBatchStarting.value) return
  isBatchStarting.value = true
  try {
    for (const item of batchItems.value) {
      if (!isBatchRunnableStatus(item.status)) {
        continue
      }
      item.queuedRetry = item.resultKind === 'script' && item.jobId && ['失败', '重试失败', '已停止'].includes(item.status)
      if (item.status !== '等待中') {
        item.status = '等待中'
        item.statusTone = 'muted'
        item.latestLog = '等待批量队列启动。'
      }
    }
    batchAutoRun.value = true
    await maybeStartNextBatchItem()
  } finally {
    isBatchStarting.value = false
  }
}

async function stopBatchItem(item) {
  if (batchAutoRun.value) {
    batchAutoRun.value = false
  }
  if (!item.jobId) {
    item.status = '已停止'
    item.statusTone = 'muted'
    item.latestLog = '任务未开始。'
    return
  }
  try {
    await fetch(`/api/jobs/${item.jobId}/stop`, { method: 'POST' }).then(readJson)
  } catch {}
  if (item.resultKind === 'script') {
    item.status = '停止中'
    item.statusTone = 'running'
    pushBatchLog(item, '已请求停止讲稿生成，当前页完成后会停止并保留草稿。', '已停止')
    startBatchPolling(item)
    return
  }
  stopBatchPolling(item.id)
  item.status = '已停止'
  item.statusTone = 'muted'
  pushBatchLog(item, '已请求停止生成任务。', '已停止')
}

async function stopAllBatchItems() {
  batchAutoRun.value = false
  await Promise.all(
    batchItems.value
      .filter((item) => item.jobId && item.statusTone === 'running')
      .map((item) => stopBatchItem(item)),
  )
}

async function retryBatchScriptJob(item) {
  if (!item.jobId || item.resultKind !== 'script') {
    return startBatchItem(item)
  }
  item.status = '排队中'
  item.statusTone = 'running'
  item.error = ''
  item.output = ''
  item.outputDownloadName = ''
  item.pptOutput = ''
  item.pptDownloadName = ''
  item.queuedRetry = false
  item.queuedStart = false
  pushBatchLog(item, '已发起重试，将复用已生成页面并继续未完成页面。', '排队中')
  try {
    await fetch(`/api/script/jobs/${item.jobId}/retry`, {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ user_id: currentUser.value }),
    }).then(readJson)
    startBatchPolling(item)
    return true
  } catch (error) {
    item.error = error.message || '重试失败'
    item.status = '重试失败'
    item.statusTone = 'muted'
    pushBatchLog(item, item.error, '失败')
    await maybeStartNextBatchItem()
    return false
  }
}

async function maybeAutoRetryBatchItem(item, reason = '') {
  if (!batchAutoRetry.value || item.resultKind !== 'script' || !item.jobId) return false
  if (item.autoRetryCount >= batchMaxAutoRetries) return false
  item.autoRetryCount += 1
  pushBatchLog(
    item,
    `任务失败，自动重试第 ${item.autoRetryCount}/${batchMaxAutoRetries} 次。${reason ? `失败原因：${reason}` : ''}`,
    '排队中',
  )
  return retryBatchScriptJob(item)
}

function batchOutputUrl(item) {
  const filename = item.resultKind === 'script' ? item.pptOutput : item.output
  const downloadName = item.resultKind === 'script' ? item.pptDownloadName : item.outputDownloadName
  return downloadLink(filename, downloadName)
}

function batchOutputFilePayload(item) {
  return {
    filename: item.resultKind === 'script' ? item.pptOutput : item.output,
    download_name: item.resultKind === 'script' ? item.pptDownloadName : item.outputDownloadName,
  }
}

async function downloadAllBatchOutputs() {
  const files = batchDownloadableItems.value
    .map(batchOutputFilePayload)
    .filter((item) => item.filename)
  if (!files.length) return
  try {
    const response = await fetch('/api/download/batch-zip', {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ files }),
    })
    if (!response.ok) {
      await readJson(response)
      return
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `批量下载-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.zip`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    const target = batchDownloadableItems.value[0]
    if (target) {
      pushBatchLog(target, error.message || '打包下载失败', '失败')
      batchExpandedId.value = target.id
    }
  }
}

function setScriptFile(file) {
  if (!file) return
  scriptFile.value = file
  scriptFileName.value = file.name
  scriptUploadId.value = ''
  scriptSlides.value = []
  generatedScripts.value = []
  scriptLogs.value = []
  scriptJobId.value = ''
  scriptJobStatus.value = ''
  scriptPptDownloadUrl.value = ''
  scriptAnalyzeMessage.value = ''
  scriptGenerateMessage.value = ''
}

function onScriptFileChange(event) {
  setScriptFile(event.target.files?.[0])
}

function onScriptDrop(event) {
  isDragging.value = false
  setScriptFile(event.dataTransfer.files?.[0])
}

async function analyzeScriptPpt() {
  if (!scriptFile.value) {
    scriptAnalyzeMessage.value = '请先上传 PPTX。'
    return
  }
  isScriptAnalyzing.value = true
  scriptAnalyzeMessage.value = '正在分析 PPT 页面内容与原备注。'
  scriptGenerateMessage.value = ''
  const formData = new FormData()
  formData.append('pptx', scriptFile.value)
  try {
    const data = await fetch('/api/script/analyze', { method: 'POST', headers: userHeaders(), body: formData }).then(readJson)
    scriptUploadId.value = data.upload_id
    scriptSlides.value = data.slides
    scriptAnalyzeMessage.value = `分析完成：共 ${data.slide_count} 页。`
  } catch {
    scriptAnalyzeMessage.value = '分析失败，请确认后端已启动。'
  } finally {
    isScriptAnalyzing.value = false
  }
}

function estimateScriptDuration() {
  const generatedText = generatedScripts.value.map((item) => item.script).join('')
  const sourceText = generatedText || scriptSlides.value.map((item) => item.note || '').join('')
  const chars = sourceText.replace(/\s+/g, '').length
  if (!chars) {
    scriptGenerateMessage.value = scriptSlides.value.length
      ? '当前 PPT 原备注为空或过短，请先生成讲稿后再预估。'
      : '请先分析课件，或生成讲稿后再预估。'
    return
  }
  const minutes = chars / 264
  scriptGenerateMessage.value = generatedText
    ? `当前生成讲稿约 ${chars} 字，预计朗读 ${minutes.toFixed(1)} 分钟。`
    : `当前原备注约 ${chars} 字，预计朗读 ${minutes.toFixed(1)} 分钟；生成讲稿后可重新预估。`
}

async function generateScripts() {
  if (!scriptUploadId.value) {
    await analyzeScriptPpt()
    if (!scriptUploadId.value) return
  }
  isScriptGenerating.value = true
  generatedScripts.value = []
  scriptLogs.value = []
  scriptGenerateMessage.value = '已创建讲稿生成任务，正在等待开始。'
  scriptPptDownloadUrl.value = ''
  try {
    const data = await fetch('/api/script/generate', {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        upload_id: scriptUploadId.value,
        user_id: currentUser.value,
        strategy: scriptStrategy.value,
        style: scriptStyle.value,
        enrichment: scriptEnrichment.value,
        short_threshold: Number(shortNoteThreshold.value) || 180,
        target_minutes: Number(scriptTargetMinutes.value) || 40,
        auto_expand_duration: autoExpandDuration.value,
      }),
    }).then(readJson)
    scriptJobId.value = data.job_id
    scriptGenerateMessage.value = '讲稿生成任务已启动，正在逐页调用 AI。'
    pollScriptJob()
  } catch (error) {
    scriptGenerateMessage.value = error.message || '讲稿生成失败，请检查 AI 设置。'
    isScriptGenerating.value = false
  }
}

async function pollScriptJob() {
  const timer = setInterval(async () => {
    try {
      const data = await fetch(`/api/jobs/${scriptJobId.value}`).then(readJson)
      scriptJobStatus.value = data.status
      if (data.logs) {
        scriptLogs.value = [...data.logs].reverse()
        const latest = data.logs[data.logs.length - 1]
        if (latest?.text) {
          scriptGenerateMessage.value = latest.text
        }
      }
      if (data.status === 'done') {
        clearInterval(timer)
        isScriptGenerating.value = false
        generatedScripts.value = data.result?.scripts || []
        if (data.result?.ppt_output) {
          scriptPptDownloadUrl.value = downloadLink(data.result.ppt_output, data.result.ppt_download_name || scriptFileName.value)
        }
        const estimated = data.result?.estimated_minutes
        const expanded = data.result?.expansion_applied
        scriptGenerateMessage.value = `讲稿生成完成，共 ${generatedScripts.value.length} 页。${estimated ? `预计讲稿时长约 ${estimated.toFixed(1)} 分钟。` : ''}${expanded ? '已自动补写一轮。' : ''}`
      }
      if (data.status === 'error') {
        clearInterval(timer)
        isScriptGenerating.value = false
        const latest = data.logs?.[data.logs.length - 1]
        scriptGenerateMessage.value = latest?.text || '讲稿生成失败，请查看日志。'
      }
    } catch (error) {
      clearInterval(timer)
      isScriptGenerating.value = false
      scriptGenerateMessage.value = error.message || '读取讲稿任务状态失败。'
    }
  }, 1500)
}

async function loadVoices() {
  voices.value = await fetch('/api/voices').then((r) => r.json())
  selectedVoice.value = voices.value.find((v) => v.id === 'zh-CN-XiaoxiaoNeural')?.id || voices.value[0]?.id || ''
}

function voiceLabel(id) {
  const voice = voices.value.find((v) => v.id === id)
  if (!voice) return id
  const gender = voice.gender === 'Female' ? '女声' : '男声'
  const locale = voice.locale === 'zh-CN' ? '普通话' : voice.locale
  return `${voice.id.replace('zh-CN-', '').replace('Neural', '')} · ${locale} · ${gender}`
}

function rateLabel(value) {
  return rates.find((item) => item.value === value)?.label || value
}

function enrichmentOption(value) {
  return enrichmentOptions.find((item) => item.value === value) || enrichmentOptions[1]
}

function subtitleStyleOption(value) {
  return subtitleStyleOptions.find((item) => item.value === value) || subtitleStyleOptions[0]
}

async function analyzeFile() {
  if (!selectedFile.value) {
    addLog('请先选择一个 PPTX 文件。', '待处理')
    return
  }
  isAnalyzing.value = true
  analyzeController.value = new AbortController()
  addLog('正在上传并分析 PPT。')
  const formData = new FormData()
  formData.append('pptx', selectedFile.value)
  try {
    const data = await fetch('/api/analyze', {
      method: 'POST',
      headers: userHeaders(),
      body: formData,
      signal: analyzeController.value.signal,
    }).then((r) => r.json())
    uploadId.value = data.upload_id
    analysis.value = data
    addLog(`分析完成：共 ${data.slides} 页，备注约 ${data.chars} 字。`, '完成')
  } catch (error) {
    if (error.name === 'AbortError') {
      addLog('已停止分析。', '已停止')
    } else {
      addLog('分析失败，请检查后端是否已启动。', '失败')
    }
  } finally {
    isAnalyzing.value = false
    analyzeController.value = null
  }
}

function stopAnalysis() {
  analyzeController.value?.abort()
}

async function estimateDuration() {
  if (!analysis.value) {
    await analyzeFile()
    if (!analysis.value) return
  }
  const baseCharsPerMinute = 264
  const multiplier = {
    '-15%': 0.85,
    '-5%': 0.95,
    '+0%': 1,
    '+10%': 1.1,
  }[selectedRate.value] || 1
  const charsPerMinute = baseCharsPerMinute * multiplier
  estimatedMinutes.value = analysis.value.chars / charsPerMinute
  addLog(`预计自然时长约 ${estimatedMinutes.value.toFixed(1)} 分钟。`, '完成')
}

async function previewVoice() {
  if (!selectedVoice.value) return
  isPreviewing.value = true
  addLog('正在生成试听音频。')
  try {
    const blob = await fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voice: selectedVoice.value,
        rate: selectedRate.value,
        text: '大家好，这是当前音色的试听效果。接下来我们将开始本页内容的讲解。',
      }),
    }).then((r) => r.blob())
    audioUrl.value = URL.createObjectURL(blob)
    addLog('试听音频已生成。', '完成')
  } catch {
    addLog('试听失败，请检查后端是否已启动。', '失败')
  } finally {
    isPreviewing.value = false
  }
}

async function generateVideo() {
  if (!uploadId.value) {
    await analyzeFile()
    if (!uploadId.value) return
  }
  isGenerating.value = true
  downloadUrl.value = ''
  addLog('已创建视频生成任务。')
  const data = await fetch('/api/generate', {
    method: 'POST',
    headers: userHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      upload_id: uploadId.value,
      user_id: currentUser.value,
      voice: selectedVoice.value,
      rate: selectedRate.value,
      subtitle_style: settings.value.subtitle_style,
      ...(useTargetDuration.value ? { target_minutes: Number(targetMinutes.value) || 40 } : {}),
    }),
  }).then((r) => r.json())
  jobId.value = data.job_id
  pollJob()
}

async function stopGeneration() {
  if (!jobId.value || !isGenerating.value) return
  await fetch(`/api/jobs/${jobId.value}/stop`, { method: 'POST' })
  isGenerating.value = false
  addLog('已请求停止视频生成。', '已停止')
}

async function pollJob() {
  const timer = setInterval(async () => {
    const data = await fetch(`/api/jobs/${jobId.value}`).then((r) => r.json())
    jobStatus.value = data.status
    if (data.logs) {
      logs.value = [...data.logs].reverse()
    }
    lastPolledStatus.value = data.status
    if (data.status === 'done') {
      clearInterval(timer)
      isGenerating.value = false
      downloadUrl.value = downloadLink(data.output, data.output_download_name || fileName.value.replace(/\.pptx$/i, '.mp4'))
      addLog('视频生成完成，可以下载。', '完成')
    }
    if (data.status === 'error') {
      clearInterval(timer)
      isGenerating.value = false
      if (!data.logs?.length) {
        addLog('视频生成失败，请查看后端日志。', '失败')
      }
    }
  }, 2500)
}

async function loadServerLogs() {
  try {
    const response = await fetch('/api/server-logs')
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    serverLogs.value = (await response.json()).reverse()
  } catch {
    addLog('无法读取后端日志，请确认后端已重启到最新版本。', '失败')
  }
}

async function loadSettings() {
  try {
    const data = await fetch('/api/settings', { headers: userHeaders() }).then(readJson)
    settings.value = {
      ...settings.value,
      ...data,
      ai_api_key: '',
    }
    scriptStyle.value = data.default_script_style || scriptStyle.value
  } catch {
    settingsMessage.value = '读取设置失败，请确认后端已启动。'
  }
}

async function saveAISettings() {
  isSavingSettings.value = true
  settingsMessage.value = ''
  try {
    const data = await fetch('/api/settings', {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ ...settings.value, user_id: currentUser.value }),
    }).then(readJson)
    settings.value = { ...settings.value, ...data, ai_api_key: '' }
    settingsMessage.value = '设置已保存。'
    clearTimeout(settingsMessageTimer)
    settingsMessageTimer = setTimeout(() => {
      settingsMessage.value = ''
    }, 2500)
  } catch (error) {
    settingsMessage.value = error.message || '保存失败，请确认后端已启动。'
  } finally {
    isSavingSettings.value = false
  }
}

async function saveSubtitleSettings() {
  isSavingSubtitleSettings.value = true
  subtitleSettingsMessage.value = ''
  try {
    const payload = { subtitle_style: settings.value.subtitle_style }
    const data = await fetch('/api/settings', {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ ...payload, user_id: currentUser.value }),
    }).then(readJson)
    settings.value = { ...settings.value, ...data, ai_api_key: '' }
    subtitleSettingsMessage.value = '字幕样式已保存。'
    clearTimeout(subtitleSettingsMessageTimer)
    subtitleSettingsMessageTimer = setTimeout(() => {
      subtitleSettingsMessage.value = ''
    }, 2500)
  } catch (error) {
    subtitleSettingsMessage.value = error.message || '保存失败，请确认后端已启动。'
  } finally {
    isSavingSubtitleSettings.value = false
  }
}

async function testAIConnection() {
  isTestingAI.value = true
  settingsMessage.value = ''
  try {
    const data = await fetch('/api/settings/test-ai', {
      method: 'POST',
      headers: userHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ ...settings.value, user_id: currentUser.value }),
    }).then(readJson)
    settingsMessage.value = data.message
  } catch (error) {
    settingsMessage.value = error.message || '测试失败，请确认后端已启动。'
  } finally {
    isTestingAI.value = false
  }
}

onMounted(() => {
  loadVoices()
  loadSettings()
  loadTokenUsage()
})

watch(selectedRate, () => {
  estimatedMinutes.value = null
})

watch(activeTab, (value) => {
  localStorage.setItem('activeTab', value)
  loadTokenUsageIfNeeded()
})
</script>

<template>
  <header class="top-navigation">
    <div class="top-navigation-inner">
      <nav class="nav-links">
        <button class="nav-link" :class="{ active: activeTab === 'single' }" @click="activeTab = 'single'">
          单个生成
        </button>
        <button class="nav-link" :class="{ active: activeTab === 'batch' }" @click="activeTab = 'batch'">
          批量生成
        </button>
        <button class="nav-link" :class="{ active: activeTab === 'script' }" @click="activeTab = 'script'">
          讲稿生成
        </button>
        <button class="nav-link" :class="{ active: activeTab === 'serverLogs' }" @click="activeTab = 'serverLogs'; loadServerLogs()">
          日志
        </button>
        <button class="nav-link nav-link-token" :class="{ active: activeTab === 'tokenUsage' }" @click="activeTab = 'tokenUsage'; loadTokenUsage()">
          <span class="nav-token-head">额度消耗</span>
        </button>
        <button class="nav-link" :class="{ active: activeTab === 'settings' }" @click="activeTab = 'settings'">
          设置
        </button>
      </nav>
    </div>
  </header>

  <main class="page">

    <template v-if="activeTab === 'single'">
    <section class="grid">
      <article class="card">
        <h2>上传课件</h2>
        <label
          class="dropzone batch-dropzone"
          :class="{ dragging: isDragging }"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
        >
          <input ref="fileInput" type="file" accept=".pptx" @change="onFileChange" />
          <FileUp :size="22" />
          <strong>拖入 PPTX，或点击选择文件</strong>
          <span>{{ fileName }}</span>
        </label>
        <div class="upload-actions">
          <button v-if="selectedFile" class="clear-file" @click="clearFile">
            清除
          </button>
          <button class="utility" @click="analyzeFile">
            <LoaderCircle v-if="isAnalyzing" :size="16" class="spin" />
            {{ isAnalyzing ? '分析中' : '分析课件' }}
          </button>
          <button v-if="isAnalyzing" class="danger" @click="stopAnalysis">
            <Square :size="15" />
            停止分析
          </button>
        </div>
        <div class="timeline">
          <div class="step">
            <b>01</b>
            <span>提取备注</span>
          </div>
          <div class="step">
            <b>02</b>
            <span>生成配音</span>
          </div>
          <div class="step">
            <b>03</b>
            <span>合成视频</span>
          </div>
        </div>
      </article>

      <article class="card">
        <h2>讲解设置</h2>
        <div class="form">
          <label>
            <span>中文音色</span>
            <div class="select">
              <button class="select-trigger" @click="voiceOpen = !voiceOpen">
                {{ voiceLabel(selectedVoice) }}
                <ChevronDown :size="18" />
              </button>
              <div v-if="voiceOpen" class="select-menu">
                <button
                  v-for="voice in voices"
                  :key="voice.id"
                  class="select-option"
                  :class="{ active: voice.id === selectedVoice }"
                  @click="selectedVoice = voice.id; voiceOpen = false"
                >
                  <Check v-if="voice.id === selectedVoice" :size="16" />
                  <span>{{ voiceLabel(voice.id) }}</span>
                </button>
              </div>
            </div>
          </label>

          <label>
            <span>语速</span>
            <div class="select">
              <button class="select-trigger" @click="rateOpen = !rateOpen">
                {{ rateLabel(selectedRate) }}
                <ChevronDown :size="18" />
              </button>
              <div v-if="rateOpen" class="select-menu">
                <button
                  v-for="rate in rates"
                  :key="rate.value"
                  class="select-option"
                  :class="{ active: rate.value === selectedRate }"
                  @click="selectedRate = rate.value; rateOpen = false"
                >
                  <Check v-if="rate.value === selectedRate" :size="16" />
                  <span>{{ rate.label }}</span>
                </button>
              </div>
            </div>
          </label>

          <div>
            <span class="duration-label">
              自定义目标时长
              <span class="tooltip-wrap">
                <CircleHelp :size="15" />
                <span class="tooltip">
                  开启后，系统会通过页尾停顿尽量接近目标总时长；关闭时，则按 PPT 的自然配音时长生成。
                </span>
              </span>
            </span>
            <div class="duration-row">
              <button class="toggle" :class="{ enabled: useTargetDuration }" @click="useTargetDuration = !useTargetDuration">
                <span></span>
              </button>
              <div class="duration-input" :class="{ disabled: !useTargetDuration }">
                <input v-model="targetMinutes" type="number" min="1" step="1" :disabled="!useTargetDuration" />
                <span>分钟</span>
              </div>
            </div>
          </div>
        </div>

        <div class="actions">
          <button class="primary" @click="generateVideo">
            <LoaderCircle v-if="isGenerating" :size="16" class="spin" />
            {{ isGenerating ? '生成中' : '开始生成' }}
          </button>
          <button class="secondary" @click="previewVoice">
            <LoaderCircle v-if="isPreviewing" :size="16" class="spin" />
            {{ isPreviewing ? '生成试听中' : '试听音色' }}
          </button>
          <button class="secondary" @click="estimateDuration">
            估算自然时长
          </button>
          <button v-if="isGenerating" class="danger" @click="stopGeneration">
            <Square :size="15" />
            停止生成
          </button>
        </div>
        <a v-if="downloadUrl" class="download" :href="downloadUrl">
          <Download :size="16" />
          下载生成视频
        </a>
        <audio v-if="audioUrl" class="audio" :src="audioUrl" controls autoplay />
      </article>
    </section>

    <section class="card log">
      <div class="section-head">
        <div class="section-title">
          <h2>追踪日志</h2>
          <span>
            {{
              analysis
                ? `共 ${analysis.slides} 页 · 备注 ${analysis.chars} 字${estimatedMinutes ? ` · 预计 ${estimatedMinutes.toFixed(1)} 分钟` : ''}`
                : '等待课件分析'
            }}
          </span>
        </div>
        <div class="section-tools">
          <button class="utility compact" @click="clearLogs">清空日志</button>
        </div>
      </div>
      <div class="log-list">
        <div v-if="!logs.length" class="empty-log">尚未开始任务。</div>
        <div v-for="item in logs" :key="item.time + item.text" class="log-item">
          <span class="log-time">{{ item.time }}</span>
          <span>{{ item.text }}</span>
          <span class="log-state" :class="{ done: item.state === '完成' }">{{ item.state }}</span>
        </div>
      </div>
    </section>
    </template>

    <template v-else-if="activeTab === 'batch'">
      <section class="batch-layout">
        <article class="card batch-upload">
          <h2>批量上传</h2>
          <label
            class="dropzone batch-dropzone"
            :class="{ dragging: isDragging }"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onBatchDrop"
          >
            <input ref="batchFileInput" type="file" accept=".pptx" multiple @change="onBatchFilesChange" />
            <FileUp :size="22" />
            <strong>拖入多个 PPTX，或点击选择文件</strong>
            <span>{{ batchItems.length ? `已加入 ${batchItems.length} 个文件` : '支持一次处理多份课件' }}</span>
          </label>
          <div class="upload-actions">
            <button class="primary" @click="startAllBatchItems">
              <LoaderCircle v-if="isBatchStarting" :size="16" class="spin" />
              {{ isBatchStarting ? '启动中' : '全部开始' }}
            </button>
            <button class="danger" @click="stopAllBatchItems">全部停止</button>
            <button v-if="batchItems.length" class="clear-file" @click="clearBatchQueue">清空队列</button>
          </div>
        </article>

        <article class="card batch-settings">
          <h2>批量设置</h2>
          <div class="batch-mode-bar">
            <div class="batch-mode-switch">
              <button class="strategy-pill" :class="{ active: batchMode === 'video' }" @click="batchMode = 'video'">
                视频
              </button>
              <button class="strategy-pill" :class="{ active: batchMode === 'script' }" @click="batchMode = 'script'">
                讲稿
              </button>
            </div>
            <div class="batch-concurrency">
              <span>
                并发数
                <span class="tooltip-wrap tooltip-wrap-down">
                  <CircleHelp :size="15" />
                  <span class="tooltip">这里限制当前浏览器批量启动数量；后端讲稿任务默认每用户最多并行 3 个，同时保留服务器全局上限，超出会进入排队中。</span>
                </span>
              </span>
              <div class="batch-mode-switch batch-mode-inline">
                <button class="strategy-pill" :class="{ active: batchConcurrency === '1' }" @click="batchConcurrency = '1'">1</button>
                <button class="strategy-pill" :class="{ active: batchConcurrency === '2' }" @click="batchConcurrency = '2'">2</button>
                <button class="strategy-pill" :class="{ active: batchConcurrency === '3' }" @click="batchConcurrency = '3'">3</button>
              </div>
            </div>
            <div v-if="batchMode === 'script' && ['duration', 'auto'].includes(batchScriptStrategy)" class="batch-inline-toggle">
              <span class="duration-label batch-inline-label">
                自动补写
                <span class="tooltip-wrap tooltip-wrap-down">
                  <CircleHelp :size="15" />
                  <span class="tooltip">批量按目标时长生成时，首轮偏短会自动补写一轮。</span>
                </span>
              </span>
              <button class="toggle" :class="{ enabled: batchAutoExpandDuration }" @click="batchAutoExpandDuration = !batchAutoExpandDuration">
                <span></span>
              </button>
            </div>
            <div v-if="batchMode === 'script'" class="batch-inline-toggle">
              <span class="duration-label batch-inline-label">
                失败自动重试
                <span class="tooltip-wrap tooltip-wrap-down">
                  <CircleHelp :size="15" />
                  <span class="tooltip">讲稿任务失败后自动复用已生成页面继续重试，最多自动重试 2 次，避免重复消耗已完成页面的 token。</span>
                </span>
              </span>
              <button class="toggle" :class="{ enabled: batchAutoRetry }" @click="batchAutoRetry = !batchAutoRetry">
                <span></span>
              </button>
            </div>
          </div>
          <div class="form">
            <template v-if="batchMode === 'video'">
              <label>
                <span>统一音色</span>
                <div class="select">
                  <button class="select-trigger" @click="batchVoiceOpen = !batchVoiceOpen">
                    {{ voiceLabel(selectedVoice) }}
                    <ChevronDown :size="18" />
                  </button>
                  <div v-if="batchVoiceOpen" class="select-menu">
                    <button
                      v-for="voice in voices"
                      :key="voice.id"
                      class="select-option"
                      :class="{ active: voice.id === selectedVoice }"
                      @click="selectedVoice = voice.id; batchVoiceOpen = false"
                    >
                      <Check v-if="voice.id === selectedVoice" :size="16" />
                      <span>{{ voiceLabel(voice.id) }}</span>
                    </button>
                  </div>
                </div>
              </label>
              <label>
                <span>统一语速</span>
                <div class="select">
                  <button class="select-trigger" @click="batchRateOpen = !batchRateOpen">
                    {{ rateLabel(selectedRate) }}
                    <ChevronDown :size="18" />
                  </button>
                  <div v-if="batchRateOpen" class="select-menu">
                    <button
                      v-for="rate in rates"
                      :key="rate.value"
                      class="select-option"
                      :class="{ active: rate.value === selectedRate }"
                      @click="selectedRate = rate.value; batchRateOpen = false"
                    >
                      <Check v-if="rate.value === selectedRate" :size="16" />
                      <span>{{ rate.label }}</span>
                    </button>
                  </div>
                </div>
              </label>
              <div>
                <span class="duration-label">
                  统一目标时长
                  <span class="tooltip-wrap">
                    <CircleHelp :size="15" />
                    <span class="tooltip">
                      开启后，每个文件都会按同一目标总时长策略生成；关闭时，全部按自然时长生成。
                    </span>
                  </span>
                </span>
                <div class="duration-row">
                  <button class="toggle" :class="{ enabled: batchUseTargetDuration }" @click="batchUseTargetDuration = !batchUseTargetDuration">
                    <span></span>
                  </button>
                  <div class="duration-input" :class="{ disabled: !batchUseTargetDuration }">
                    <input v-model="batchTargetMinutes" type="number" min="1" step="1" :disabled="!batchUseTargetDuration" />
                    <span>分钟</span>
                  </div>
                </div>
              </div>
            </template>
            <template v-else>
              <label>
                <span>生成策略</span>
                <div class="batch-mode-switch batch-mode-inline">
                  <button class="strategy-pill" :class="{ active: batchScriptStrategy === 'short' }" @click="batchScriptStrategy = 'short'">
                    只补短备注
                  </button>
                  <button class="strategy-pill" :class="{ active: batchScriptStrategy === 'rewrite' }" @click="batchScriptStrategy = 'rewrite'">
                    全部重写
                  </button>
                  <button class="strategy-pill" :class="{ active: batchScriptStrategy === 'duration' }" @click="batchScriptStrategy = 'duration'">
                    按目标时长生成
                  </button>
                  <button class="strategy-pill" :class="{ active: batchScriptStrategy === 'auto' }" @click="batchScriptStrategy = 'auto'">
                    自动化
                  </button>
                </div>
              </label>
              <div class="batch-script-row" :class="{ single: !['short', 'duration', 'auto'].includes(batchScriptStrategy) }">
                <label>
                  <span>讲解风格</span>
                  <input v-model="batchScriptStyle" />
                </label>
                <div v-if="batchScriptStrategy === 'short'">
                  <span>短备注阈值</span>
                  <div class="duration-input">
                    <input v-model="batchShortNoteThreshold" type="number" min="1" step="10" />
                    <span>字</span>
                  </div>
                </div>
                <div v-if="batchScriptStrategy === 'duration'">
                  <span>统一目标讲稿时长</span>
                  <div class="duration-input">
                    <input v-model="batchScriptTargetMinutes" type="number" min="1" step="1" />
                    <span>分钟</span>
                  </div>
                </div>
                <div v-if="batchScriptStrategy === 'auto'">
                  <span>页数倍数</span>
                  <div class="duration-input">
                    <input v-model="batchScriptAutoPageMultiplier" type="number" min="0.1" step="0.1" />
                    <span>倍</span>
                  </div>
                </div>
              </div>
              <label>
                <span>补充程度</span>
                <div class="select">
                  <button class="select-trigger" @click="batchEnrichmentOpen = !batchEnrichmentOpen">
                    <span class="select-summary">
                      <strong>{{ enrichmentOption(batchScriptEnrichment).label }}</strong>
                      <span>{{ enrichmentOption(batchScriptEnrichment).hint }}</span>
                    </span>
                    <ChevronDown :size="18" />
                  </button>
                  <div v-if="batchEnrichmentOpen" class="select-menu">
                    <button
                      v-for="option in enrichmentOptions"
                      :key="option.value"
                      class="select-option select-option-detail"
                      :class="{ active: batchScriptEnrichment === option.value }"
                      @click="batchScriptEnrichment = option.value; batchEnrichmentOpen = false"
                    >
                      <Check v-if="batchScriptEnrichment === option.value" :size="16" />
                      <span>
                        <strong>{{ option.label }}</strong>
                        <small>{{ option.hint }}</small>
                      </span>
                    </button>
                  </div>
                </div>
              </label>
            </template>
          </div>
        </article>

        <article class="card batch-table">
          <div class="section-head">
            <div class="section-title">
              <h2>任务队列</h2>
              <span>{{ batchItems.length ? `${batchItems.length} 个文件` : '等待加入文件' }}</span>
            </div>
            <button
              v-if="batchDownloadableItems.length"
              class="primary compact"
              @click="downloadAllBatchOutputs"
            >
              <Download :size="15" />
              全部下载
            </button>
          </div>
          <div class="queue-list">
            <div v-if="!batchItems.length" class="empty-log">
              还没有批量任务，先拖入多个 PPTX 文件。
            </div>
            <div v-for="item in batchItems" :key="item.id" class="queue-item">
              <div class="queue-row">
                <span class="queue-file">
                  <strong>{{ item.name }}</strong>
                  <small>{{ item.latestLog }}</small>
                </span>
                <span class="muted">{{ item.slides ? `${item.slides} 页` : '待分析' }}</span>
                <span :class="batchStatusClass(item)">{{ item.status }}</span>
                <div class="queue-actions">
                  <a v-if="item.output || item.pptOutput" class="primary compact" :href="batchOutputUrl(item)">
                    <Download :size="15" />
                    {{ item.resultKind === 'script' ? '下载 PPT' : '下载视频' }}
                  </a>
                  <button v-else-if="item.statusTone === 'running'" class="danger compact" @click="stopBatchItem(item)">停止</button>
                  <button v-else-if="item.resultKind === 'script' && item.jobId && ['失败', '重试失败'].includes(item.status)" class="utility compact" @click="retryBatchScriptJob(item)">重试</button>
                  <button v-else class="utility compact" @click="startBatchItem(item)">开始</button>
                  <button class="utility compact" @click="batchExpandedId = batchExpandedId === item.id ? '' : item.id">详情</button>
                  <button class="utility compact" @click="removeBatchItem(item.id)">移除</button>
                </div>
              </div>
              <div v-if="batchExpandedId === item.id" class="batch-detail">
                <div class="batch-detail-meta">
                  <span>备注字数：{{ item.chars ?? '待分析' }}</span>
                  <span>任务 ID：{{ item.jobId || '尚未创建' }}</span>
                  <span v-if="item.resultKind === 'script'">自动重试：{{ item.autoRetryCount }}/{{ batchMaxAutoRetries }}</span>
                  <span v-if="item.resultKind === 'script' && item.automatedTargetMinutes">自动化目标：{{ item.automatedTargetMinutes }} 分钟</span>
                  <span v-if="item.resultKind === 'script' && item.estimatedMinutes">预计讲稿时长：{{ item.estimatedMinutes.toFixed(1) }} 分钟</span>
                </div>
                <div class="batch-log-list">
                  <div v-if="!item.logs.length" class="empty-log">还没有日志。</div>
                  <div v-for="log in item.logs" :key="`${log.time}-${log.text}`" class="batch-log-item">
                    <span>{{ log.time }}</span>
                    <span>{{ log.text }}</span>
                    <span>{{ log.state }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>

    <template v-else-if="activeTab === 'script'">
      <section class="script-layout">
        <article class="card script-upload">
          <h2>上传课件</h2>
          <label
            class="dropzone batch-dropzone"
            :class="{ dragging: isDragging }"
            @dragenter.prevent="isDragging = true"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onScriptDrop"
          >
            <input ref="scriptFileInput" type="file" accept=".pptx" @change="onScriptFileChange" />
            <FileUp :size="22" />
            <strong>上传需要生成讲稿的 PPTX</strong>
            <span>{{ scriptFileName }}</span>
          </label>
          <div class="script-control-row">
            <div class="script-analyze-block">
              <button class="utility" @click="analyzeScriptPpt">
                <LoaderCircle v-if="isScriptAnalyzing" :size="16" class="spin" />
                {{ isScriptAnalyzing ? '分析中' : '分析课件' }}
              </button>
              <p v-if="scriptAnalyzeMessage" class="script-local-message">{{ scriptAnalyzeMessage }}</p>
            </div>
            <div class="script-strategy-actions">
              <button
                class="strategy-pill"
                :class="{ active: scriptStrategy === 'short' }"
                @click="scriptStrategy = 'short'; activeStrategyPopover = activeStrategyPopover === 'short' ? '' : 'short'"
              >
                只补短备注
                <span>备注过短的页面才扩写，适合已有基础讲稿的 PPT。</span>
              </button>
              <button
                class="strategy-pill"
                :class="{ active: scriptStrategy === 'rewrite' }"
                @click="scriptStrategy = 'rewrite'; activeStrategyPopover = ''"
              >
                全部重写
                <span>按统一讲师风格重写每页讲解词。</span>
              </button>
              <button
                class="strategy-pill"
                :class="{ active: scriptStrategy === 'duration' }"
                @click="scriptStrategy = 'duration'; activeStrategyPopover = activeStrategyPopover === 'duration' ? '' : 'duration'"
              >
                按目标时长生成
                <span>根据期望总时长分配每页字数，比硬加停顿更自然。</span>
              </button>
              <div v-if="activeStrategyPopover === 'short'" class="strategy-popover">
                <label>
                  <span>短备注阈值</span>
                  <div class="duration-input">
                    <input v-model="shortNoteThreshold" type="number" min="1" step="10" />
                    <span>字</span>
                  </div>
                </label>
              </div>
              <div v-if="activeStrategyPopover === 'duration'" class="strategy-popover duration-popover">
                <label>
                  <span>目标讲稿总时长</span>
                  <div class="duration-input">
                    <input v-model="scriptTargetMinutes" type="number" min="1" step="1" />
                    <span>分钟</span>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </article>

        <article class="card script-style">
          <h2>讲解风格</h2>
          <div class="form">
            <label>
              <span>风格</span>
              <div class="select">
                <button class="select-trigger">
                  <input v-model="scriptStyle" class="inline-style-input" />
                </button>
              </div>
            </label>
            <label>
              <span>补充程度</span>
              <div class="select">
                <button class="select-trigger" @click="enrichmentOpen = !enrichmentOpen">
                  <span class="select-summary">
                    <strong>{{ enrichmentOption(scriptEnrichment).label }}</strong>
                    <span>{{ enrichmentOption(scriptEnrichment).hint }}</span>
                  </span>
                  <ChevronDown :size="18" />
                </button>
                <div v-if="enrichmentOpen" class="select-menu">
                  <button
                    v-for="option in enrichmentOptions"
                    :key="option.value"
                    class="select-option select-option-detail"
                    :class="{ active: scriptEnrichment === option.value }"
                    @click="scriptEnrichment = option.value; enrichmentOpen = false"
                  >
                    <Check v-if="option.value === scriptEnrichment" :size="16" />
                    <span>
                      <strong>{{ option.label }}</strong>
                      <small>{{ option.hint }}</small>
                    </span>
                  </button>
                </div>
              </div>
            </label>
          </div>
          <div class="writeback-option">
            <button class="toggle" :class="{ enabled: autoExpandDuration }" @click="autoExpandDuration = !autoExpandDuration">
              <span></span>
            </button>
            <div>
              <strong>时长不足自动补写</strong>
              <p style="font-size: 14px; color: var(--ink-soft);">首轮讲稿偏短时会在原稿基础上自动补写一轮。</p>
            </div>
          </div>
          <div class="actions">
            <button class="primary" @click="generateScripts">
              <LoaderCircle v-if="isScriptGenerating" :size="16" class="spin" />
              {{ isScriptGenerating ? '生成中' : '生成讲稿' }}
            </button>
            <button class="secondary" @click="estimateScriptDuration">预估讲稿时长</button>
            <a v-if="scriptPptDownloadUrl" class="download inline-download" :href="scriptPptDownloadUrl">
              <Download :size="16" />
              下载 PPT
            </a>
          </div>
          <p v-if="scriptGenerateMessage" class="settings-message">{{ scriptGenerateMessage }}</p>
        </article>

        <article class="card script-dual-panel">
          <section class="script-panel-column">
            <div class="section-head">
              <div class="section-title">
                <h2>讲稿结果</h2>
                <span>显示每页生成的讲稿内容</span>
              </div>
              <div class="section-tools">
                <button class="utility compact">保存为备注</button>
                <button class="utility compact">进入单个生成</button>
              </div>
            </div>
            <div class="script-pages">
              <div v-if="!generatedScripts.length" class="empty-log">
                {{ scriptSlides.length ? '课件已分析完成；生成讲稿后，这里会显示逐页结果。' : '上传并分析 PPT 后，这里会显示逐页讲稿结果。' }}
              </div>
              <div v-for="item in generatedScripts" :key="item.index" class="script-page">
                <div>
                  <strong>第 {{ item.index }} 页 · {{ item.title }}</strong>
                  <p>{{ item.script }}</p>
                </div>
                <button class="utility compact">编辑</button>
              </div>
            </div>
          </section>

          <section class="script-panel-column script-panel-log">
            <div class="section-head">
              <div class="section-title">
                <h2>讲稿生成日志</h2>
                <span>显示讲稿任务的页级进度和失败信息</span>
              </div>
            </div>
            <div class="server-log-list">
              <div v-if="!scriptLogs.length" class="empty-log">
                {{ isScriptGenerating ? '任务已创建，等待返回首条进度日志。' : '尚未开始讲稿生成任务。' }}
              </div>
              <div v-for="item in scriptLogs" :key="item.time + item.text" class="server-log-item">
                <span>{{ item.time }}</span>
                <pre :class="{ error: item.state === '失败' }">{{ item.text }}</pre>
              </div>
            </div>
          </section>
        </article>
      </section>
    </template>

    <template v-else-if="activeTab === 'tokenUsage'">
      <section class="token-usage-layout">
        <article class="card token-usage-card">
          <div class="section-head">
            <div class="section-title">
              <h2>Token 消耗</h2>
            </div>
            <div class="section-tools">
              <button class="utility compact" @click="loadTokenUsage">刷新</button>
            </div>
          </div>
          <div class="token-usage-summary">
            <div class="token-metric">
              <span>累计费用</span>
              <strong>{{ formatUsd(tokenUsage.totals.total_cost) }}</strong>
            </div>
            <div class="token-metric">
              <span>输入 Tokens</span>
              <strong>{{ formatTokenCount(tokenUsage.totals.input_tokens) }}</strong>
            </div>
            <div class="token-metric">
              <span>补全 Tokens</span>
              <strong>{{ formatTokenCount(tokenUsage.totals.completion_tokens) }}</strong>
            </div>
            <div class="token-metric">
              <span>缓存读取 Tokens</span>
              <strong>{{ formatTokenCount(tokenUsage.totals.cache_read_tokens) }}</strong>
            </div>
          </div>
          <div class="token-chart-panel">
            <div class="token-chart-block">
              <div class="token-chart-head">
                <strong>总 Token 消耗</strong>
                <span>{{ formatTokenCount(tokenUsage.totals.total_tokens) }}</span>
              </div>
              <svg class="token-chart" viewBox="0 0 640 220" aria-hidden="true">
                <polyline :points="chartPoints(historySeries('total_tokens'), 640, 220)" />
              </svg>
            </div>
          </div>
          <div class="token-history-list">
            <div v-if="!tokenUsage.history.length" class="empty-log">暂时还没有 AI 调用记录。</div>
            <div v-for="item in [...tokenUsage.history].reverse()" :key="item.time + item.total_tokens" class="token-history-item">
              <span>{{ item.time }}</span>
              <div>
                <strong>{{ formatUsd(item.total_cost) }}</strong>
                <p>输入 {{ formatTokenCount(item.input_tokens) }} / 补全 {{ formatTokenCount(item.completion_tokens) }} / 缓存 {{ formatTokenCount(item.cache_read_tokens) }}</p>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>

    <template v-else-if="activeTab === 'settings'">
      <section class="settings-layout">
        <article class="card settings-card">
          <div class="section-head">
            <div class="section-title">
              <h2>AI 设置</h2>
            </div>
          </div>
          <div class="form">
            <label>
              <span>Base URL</span>
              <input v-model="settings.ai_base_url" placeholder="https://api.openai.com/v1" />
            </label>
            <label>
              <span>API Key</span>
              <input
                v-model="settings.ai_api_key"
                type="password"
                :placeholder="settings.has_api_key ? '已保存；留空则不修改' : '请输入 API Key'"
              />
            </label>
            <label>
              <span>Model</span>
              <input v-model="settings.ai_model" placeholder="gpt-4.1-mini" />
            </label>
            <label class="checkbox-field">
              <input v-model="settings.ai_verify_ssl" type="checkbox" />
              <span>校验 SSL 证书</span>
            </label>
            <label>
              <span>默认讲解风格</span>
              <input v-model="settings.default_script_style" />
            </label>
          </div>
          <div class="settings-actions">
            <button class="primary" @click="saveAISettings">
              {{ isSavingSettings ? '保存中' : '保存设置' }}
            </button>
            <button class="secondary" @click="testAIConnection">
              {{ isTestingAI ? '测试中' : '测试连接' }}
            </button>
          </div>
          <p v-if="settingsMessage" class="settings-message">{{ settingsMessage }}</p>
        </article>

        <article class="card settings-card">
          <h2>说明</h2>
          <div class="settings-note">
            <p>API Key 会按当前用户保存在本机 <code>backend/storage/settings.json</code></p>
            <p>Base URL 建议填写 OpenAI 兼容接口根路径</p>
            <p>例如 <code>https://api.openai.com/v1</code>。</p>
            <p>如果你使用的是自签名证书、公司网关或中转服务，可先关闭“校验 SSL 证书”再测试。</p>
            <p>讲稿生成页会读取这里的配置；没有配置时，不应发起 AI 生成。</p>
          </div>
        </article>

        <article class="card settings-card subtitle-settings-card">
          <div class="section-head">
            <div class="section-title">
              <h2>字幕样式</h2>
            </div>
          </div>
          <div class="subtitle-style-grid">
            <button
              v-for="option in subtitleStyleOptions"
              :key="option.value"
              class="subtitle-style-card"
              :class="[option.value, { active: settings.subtitle_style === option.value }]"
              @click="settings.subtitle_style = option.value"
            >
              <div class="subtitle-preview-frame">
                <div class="subtitle-preview-bg"></div>
                <div class="subtitle-preview-text">{{ option.sample }}</div>
              </div>
              <div class="subtitle-style-copy">
                <strong>{{ option.label }}</strong>
                <span>{{ option.hint }}</span>
              </div>
              <Check v-if="settings.subtitle_style === option.value" :size="16" class="subtitle-style-check" />
            </button>
          </div>
          <div class="settings-actions">
            <button class="primary" @click="saveSubtitleSettings">
              {{ isSavingSubtitleSettings ? '保存中' : '保存字幕样式' }}
            </button>
          </div>
          <p v-if="subtitleSettingsMessage" class="settings-message">{{ subtitleSettingsMessage }}</p>
        </article>

        <article class="card settings-card current-user-card">
          <div class="section-head">
            <div class="section-title">
              <h2>当前用户</h2>
            </div>
          </div>
          <div class="readonly-user">
            <span>本机浏览器用户</span>
            <strong>{{ currentUser }}</strong>
          </div>
          <p class="settings-message muted">该用户标识用于区分任务和后端日志，不可在页面中更改。</p>
        </article>
      </section>
    </template>

    <template v-else>
      <section class="server-logs-layout">
        <article class="card">
          <div class="section-head">
            <div class="section-title">
              <h2>后端日志</h2>
            </div>
            <div class="section-tools">
              <button class="utility compact" @click="loadServerLogs">刷新</button>
            </div>
          </div>
          <div class="server-log-list server-log-list-tall">
            <div v-if="!serverLogs.length" class="empty-log">暂无后端日志。</div>
            <div
              v-for="item in serverLogs"
              :key="item.time + item.text"
              class="server-log-item server-log-user-item"
              :class="{ 'has-user': logUser(item.text) }"
              :style="logUserTone(logUser(item.text))"
            >
              <span class="log-time">{{ item.time }}</span>
              <div class="server-log-body">
                <pre :class="{ error: item.level === 'error' }"><span v-if="logUser(item.text)" class="log-user-dot" aria-hidden="true"></span>{{ item.text }}</pre>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>
  </main>
</template>
