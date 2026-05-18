<script setup>
import { onMounted, ref, watch } from 'vue'
import { Check, ChevronDown, CircleHelp, Download, FileUp, LoaderCircle, Play, Sparkles, Square } from 'lucide-vue-next'

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
    showServerLogs.value = true
  } catch {
    addLog('无法读取后端日志，请确认后端已重启到最新版本。', '失败')
  }
}

onMounted(loadVoices)

watch(selectedRate, () => {
  estimatedMinutes.value = null
})
</script>

<template>
  <main class="page">
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
            <Sparkles v-else :size="16" />
            {{ isGenerating ? '生成中' : '开始生成' }}
          </button>
          <button class="secondary" @click="previewVoice">
            <LoaderCircle v-if="isPreviewing" :size="16" class="spin" />
            <Play v-else :size="16" />
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
        <audio v-if="audioUrl" class="audio" :src="audioUrl" controls autoplay />
      </article>
    </section>

    <section class="card log">
      <div class="section-head">
        <h2>追踪日志</h2>
        <div class="section-tools">
          <button class="utility compact" @click="loadServerLogs">查看日志</button>
          <span>
            {{
              analysis
                ? `共 ${analysis.slides} 页 · 备注 ${analysis.chars} 字${estimatedMinutes ? ` · 预计 ${estimatedMinutes.toFixed(1)} 分钟` : ''}`
                : '等待课件分析'
            }}
          </span>
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
      <a v-if="downloadUrl" class="download" :href="downloadUrl">
        <Download :size="16" />
        下载生成视频
      </a>
    </section>

    <div v-if="showServerLogs" class="modal-backdrop" @click.self="showServerLogs = false">
      <section class="modal card">
        <div class="section-head">
          <h2>后端日志</h2>
          <button class="utility compact" @click="showServerLogs = false">关闭</button>
        </div>
        <div class="server-log-list">
          <div v-if="!serverLogs.length" class="empty-log">暂无后端日志。</div>
          <div v-for="item in serverLogs" :key="item.time + item.text" class="server-log-item">
            <span>{{ item.time }}</span>
            <pre :class="{ error: item.level === 'error' }">{{ item.text }}</pre>
          </div>
        </div>
      </section>
    </div>
  </main>
</template>
