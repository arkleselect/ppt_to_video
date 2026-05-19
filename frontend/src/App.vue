<script setup>
import { onMounted, ref, watch } from 'vue'
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
const showServerLogs = ref(false)
const serverLogs = ref([])
const activeTab = ref(localStorage.getItem('activeTab') || 'single')
const settings = ref({
  ai_base_url: '',
  ai_api_key: '',
  ai_model: '',
  default_script_style: '培训讲师 · 稳妥清晰',
  has_api_key: false,
})
const settingsMessage = ref('')
const isSavingSettings = ref(false)
const isTestingAI = ref(false)
const writeScriptToPpt = ref(false)
const scriptFile = ref(null)
const scriptFileName = ref('还没有文件')
const scriptFileInput = ref(null)
const scriptUploadId = ref('')
const scriptSlides = ref([])
const generatedScripts = ref([])
const scriptStrategy = ref('short')
const scriptStyle = ref('培训讲师 · 稳妥清晰')
const isScriptAnalyzing = ref(false)
const isScriptGenerating = ref(false)
const scriptMessage = ref('')
const scriptPptDownloadUrl = ref('')

const voices = ref([])
const rates = [
  { label: '偏慢', value: '-15%' },
  { label: '自然偏稳', value: '-5%' },
  { label: '标准', value: '+0%' },
  { label: '偏快', value: '+10%' },
]
const logs = ref([])

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

function setScriptFile(file) {
  if (!file) return
  scriptFile.value = file
  scriptFileName.value = file.name
  scriptUploadId.value = ''
  scriptSlides.value = []
  generatedScripts.value = []
  scriptPptDownloadUrl.value = ''
  scriptMessage.value = ''
}

function onScriptFileChange(event) {
  setScriptFile(event.target.files?.[0])
}

async function analyzeScriptPpt() {
  if (!scriptFile.value) {
    scriptMessage.value = '请先上传 PPTX。'
    return
  }
  isScriptAnalyzing.value = true
  scriptMessage.value = '正在分析 PPT 页面内容与原备注。'
  const formData = new FormData()
  formData.append('pptx', scriptFile.value)
  try {
    const data = await fetch('/api/script/analyze', { method: 'POST', body: formData }).then((r) => r.json())
    scriptUploadId.value = data.upload_id
    scriptSlides.value = data.slides
    scriptMessage.value = `分析完成：共 ${data.slide_count} 页。`
  } catch {
    scriptMessage.value = '分析失败，请确认后端已启动。'
  } finally {
    isScriptAnalyzing.value = false
  }
}

async function generateScripts() {
  if (!scriptUploadId.value) {
    await analyzeScriptPpt()
    if (!scriptUploadId.value) return
  }
  isScriptGenerating.value = true
  scriptMessage.value = '正在调用 AI 生成讲稿，请稍候。'
  scriptPptDownloadUrl.value = ''
  try {
    const data = await fetch('/api/script/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        upload_id: scriptUploadId.value,
        strategy: scriptStrategy.value,
        style: scriptStyle.value,
        write_to_ppt: writeScriptToPpt.value,
      }),
    }).then(async (r) => {
      const body = await r.json()
      if (!r.ok) throw new Error(body.error || body.message || '生成失败')
      return body
    })
    generatedScripts.value = data.scripts
    if (data.ppt_output) {
      scriptPptDownloadUrl.value = `/api/download/${data.ppt_output}`
    }
    scriptMessage.value = `讲稿生成完成，共 ${data.scripts.length} 页。`
  } catch (error) {
    scriptMessage.value = error.message || '讲稿生成失败，请检查 AI 设置。'
  } finally {
    isScriptGenerating.value = false
  }
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      upload_id: uploadId.value,
      voice: selectedVoice.value,
      rate: selectedRate.value,
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
      downloadUrl.value = `/api/download/${data.output}`
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
    serverLogs.value = await response.json()
    showServerLogs.value = !showServerLogs.value
  } catch {
    addLog('无法读取后端日志，请确认后端已重启到最新版本。', '失败')
  }
}

async function loadSettings() {
  try {
    const data = await fetch('/api/settings').then((r) => r.json())
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings.value),
    }).then((r) => r.json())
    settings.value = { ...settings.value, ...data, ai_api_key: '' }
    settingsMessage.value = '设置已保存。'
  } catch {
    settingsMessage.value = '保存失败，请确认后端已启动。'
  } finally {
    isSavingSettings.value = false
  }
}

async function testAIConnection() {
  isTestingAI.value = true
  settingsMessage.value = ''
  try {
    const response = await fetch('/api/settings/test-ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings.value),
    })
    const data = await response.json()
    settingsMessage.value = data.message
  } catch {
    settingsMessage.value = '测试失败，请确认后端已启动。'
  } finally {
    isTestingAI.value = false
  }
}

onMounted(() => {
  loadVoices()
  loadSettings()
})

watch(selectedRate, () => {
  estimatedMinutes.value = null
})

watch(activeTab, (value) => {
  localStorage.setItem('activeTab', value)
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
          class="dropzone"
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

          <label>
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
          </label>
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
          <button class="utility compact" @click="loadServerLogs">查看日志</button>
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
      <section v-if="showServerLogs" class="server-log-panel">
        <div class="section-head inline-log-head">
          <h2>后端日志</h2>
          <button class="utility compact" @click="showServerLogs = false">收起</button>
        </div>
        <div class="server-log-list">
          <div v-if="!serverLogs.length" class="empty-log">暂无后端日志。</div>
          <div v-for="item in serverLogs" :key="item.time + item.text" class="server-log-item">
            <span>{{ item.time }}</span>
            <pre :class="{ error: item.level === 'error' }">{{ item.text }}</pre>
          </div>
        </div>
      </section>
    </section>
    </template>

    <template v-else-if="activeTab === 'batch'">
      <section class="batch-layout">
        <article class="card batch-upload">
          <h2>批量上传</h2>
          <div class="dropzone batch-dropzone">
            <FileUp :size="22" />
            <strong>拖入多个 PPTX，或点击选择文件</strong>
            <span>支持一次处理多份课件</span>
          </div>
        </article>

        <article class="card batch-settings">
          <h2>批量设置</h2>
          <div class="form">
            <label>
              <span>统一音色</span>
              <div class="select">
                <button class="select-trigger">
                  {{ voiceLabel(selectedVoice) }}
                  <ChevronDown :size="18" />
                </button>
              </div>
            </label>
            <label>
              <span>统一语速</span>
              <div class="select">
                <button class="select-trigger">
                  {{ rateLabel(selectedRate) }}
                  <ChevronDown :size="18" />
                </button>
              </div>
            </label>
            <label>
              <span>目标时长策略</span>
              <div class="batch-policy">默认按自然时长生成</div>
            </label>
          </div>
        </article>

        <article class="card batch-table">
          <div class="section-head">
            <div class="section-title">
              <h2>任务队列</h2>
              <span>3 个文件</span>
            </div>
            <div class="section-tools">
              <button class="primary">全部开始</button>
              <button class="utility">全部停止</button>
            </div>
          </div>
          <div class="queue-list">
            <div class="queue-row">
              <span>档案展平规范培训.pptx</span>
              <span class="muted">80 页</span>
              <span class="running">生成音频 12 / 80</span>
              <button class="utility compact">详情</button>
            </div>
            <div class="queue-row">
              <span>纸质档案扫描准备.pptx</span>
              <span class="muted">42 页</span>
              <span class="muted">等待中</span>
              <button class="utility compact">详情</button>
            </div>
            <div class="queue-row">
              <span>档案修复安全须知.pptx</span>
              <span class="muted">36 页</span>
              <span class="done">已完成</span>
              <button class="utility compact">下载</button>
            </div>
          </div>
        </article>
      </section>
    </template>

    <template v-else-if="activeTab === 'script'">
      <section class="script-layout">
        <article class="card script-upload">
          <h2>上传课件</h2>
          <label class="dropzone batch-dropzone">
            <input ref="scriptFileInput" type="file" accept=".pptx" @change="onScriptFileChange" />
            <FileUp :size="22" />
            <strong>上传需要生成讲稿的 PPTX</strong>
            <span>{{ scriptFileName }}</span>
          </label>
          <div class="script-strategy-actions">
            <button class="strategy-pill" :class="{ active: scriptStrategy === 'short' }" @click="scriptStrategy = 'short'">
              只补短备注
              <span>备注过短的页面才扩写，适合已有基础讲稿的 PPT。</span>
            </button>
            <button class="strategy-pill" :class="{ active: scriptStrategy === 'rewrite' }" @click="scriptStrategy = 'rewrite'">
              全部重写
              <span>按统一讲师风格重写每页讲解词。</span>
            </button>
            <button class="strategy-pill" :class="{ active: scriptStrategy === 'duration' }" @click="scriptStrategy = 'duration'">
              按目标时长生成
              <span>根据期望总时长分配每页字数，比硬加停顿更自然。</span>
            </button>
          </div>
          <div class="upload-actions">
            <button class="utility" @click="analyzeScriptPpt">
              <LoaderCircle v-if="isScriptAnalyzing" :size="16" class="spin" />
              {{ isScriptAnalyzing ? '分析中' : '分析课件' }}
            </button>
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
              <div class="batch-policy">只基于 PPT 内容，允许少量背景解释</div>
            </label>
          </div>
          <label class="writeback-option">
            <button class="toggle" :class="{ enabled: writeScriptToPpt }" @click="writeScriptToPpt = !writeScriptToPpt">
              <span></span>
            </button>
            <div>
              <strong>生成后写入新的 PPT 副本</strong>
            </div>
          </label>
          <div class="actions">
            <button class="primary" @click="generateScripts">
              <LoaderCircle v-if="isScriptGenerating" :size="16" class="spin" />
              {{ isScriptGenerating ? '生成中' : '生成讲稿' }}
            </button>
            <button class="secondary">预估讲稿时长</button>
            <a v-if="scriptPptDownloadUrl" class="download inline-download" :href="scriptPptDownloadUrl">
              <Download :size="16" />
              下载 PPT
            </a>
          </div>
          <p v-if="scriptMessage" class="settings-message">{{ scriptMessage }}</p>
        </article>

        <article class="card script-preview">
          <div class="section-head">
            <div class="section-title">
              <h2>讲稿预览</h2>
              <span>逐页确认后，可进入视频生成</span>
            </div>
            <div class="section-tools">
              <button class="utility compact">保存为备注</button>
              <button class="utility compact">进入单个生成</button>
            </div>
          </div>
          <div class="script-pages">
            <div v-if="!generatedScripts.length" class="empty-log">
              {{ scriptSlides.length ? '已分析课件，等待生成讲稿。' : '上传并分析 PPT 后，这里会显示逐页讲稿。' }}
            </div>
            <div v-for="item in generatedScripts" :key="item.index" class="script-page">
              <div>
                <strong>第 {{ item.index }} 页 · {{ item.title }}</strong>
                <p>{{ item.script }}</p>
              </div>
              <button class="utility compact">编辑</button>
            </div>
          </div>
        </article>
      </section>
    </template>

    <template v-else>
      <section class="settings-layout">
        <article class="card settings-card">
          <div class="section-head">
            <div class="section-title">
              <h2>AI 设置</h2>
              <span>配置 OpenAI 兼容接口，用于讲稿生成</span>
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
            <p>API Key 会保存在本机 <code>backend/storage/settings.json</code></p>
            <p>Base URL 建议填写 OpenAI 兼容接口根路径</p>
            <p>例如 <code>https://api.openai.com/v1</code>。</p>
            <p>讲稿生成页会读取这里的配置；没有配置时，不应发起 AI 生成。</p>
          </div>
        </article>
      </section>
    </template>
  </main>
</template>
