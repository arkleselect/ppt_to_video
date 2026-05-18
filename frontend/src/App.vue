<script setup>
import { computed, ref } from 'vue'
import { Check, ChevronDown, FileUp, Play, Sparkles } from 'lucide-vue-next'

const fileName = ref('还没有文件')
const selectedVoice = ref('晓晓 · 普通话 · 女声')
const selectedRate = ref('自然偏稳')
const voiceOpen = ref(false)
const rateOpen = ref(false)

const voices = ['晓晓 · 普通话 · 女声', '云健 · 普通话 · 男声']
const rates = ['自然偏稳', '标准', '偏慢']

const logs = [
  { time: '14:02:11', text: '已读取 PPT，发现 80 页，备注完整。', state: '完成' },
  { time: '14:02:19', text: '已清理页码与日期噪音。', state: '完成' },
  { time: '14:02:44', text: '正在生成中文配音，第 12 / 80 页。', state: '进行中' },
]

function onFileChange(event) {
  fileName.value = event.target.files?.[0]?.name || '还没有文件'
}
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">声</div>
        <span>Archive Voice Studio</span>
      </div>
      <div class="meta">Local workspace · Chinese narration</div>
    </header>

    <section class="grid">
      <article class="card">
        <h2>上传课件</h2>
        <label class="dropzone">
          <input type="file" accept=".pptx" @change="onFileChange" />
          <FileUp :size="22" />
          <strong>拖入 PPTX，或点击选择文件</strong>
          <span>{{ fileName }}</span>
        </label>
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
                {{ selectedVoice }}
                <ChevronDown :size="18" />
              </button>
              <div v-if="voiceOpen" class="select-menu">
                <button
                  v-for="voice in voices"
                  :key="voice"
                  class="select-option"
                  :class="{ active: voice === selectedVoice }"
                  @click="selectedVoice = voice; voiceOpen = false"
                >
                  <Check v-if="voice === selectedVoice" :size="16" />
                  <span>{{ voice }}</span>
                </button>
              </div>
            </div>
          </label>

          <label>
            <span>语速</span>
            <div class="select">
              <button class="select-trigger" @click="rateOpen = !rateOpen">
                {{ selectedRate }}
                <ChevronDown :size="18" />
              </button>
              <div v-if="rateOpen" class="select-menu">
                <button
                  v-for="rate in rates"
                  :key="rate"
                  class="select-option"
                  :class="{ active: rate === selectedRate }"
                  @click="selectedRate = rate; rateOpen = false"
                >
                  <Check v-if="rate === selectedRate" :size="16" />
                  <span>{{ rate }}</span>
                </button>
              </div>
            </div>
          </label>

          <label>
            <span>目标时长</span>
            <input value="40 分钟" />
          </label>
        </div>

        <div class="actions">
          <button class="primary">
            <Sparkles :size="16" />
            开始生成
          </button>
          <button class="secondary">
            <Play :size="16" />
            试听音色
          </button>
        </div>
      </article>
    </section>

    <section class="card log">
      <div class="section-head">
        <h2>追踪日志</h2>
        <span>当前任务 #AVS-0241</span>
      </div>
      <div class="log-list">
        <div v-for="item in logs" :key="item.time + item.text" class="log-item">
          <span class="log-time">{{ item.time }}</span>
          <span>{{ item.text }}</span>
          <span class="log-state" :class="{ done: item.state === '完成' }">{{ item.state }}</span>
        </div>
      </div>
    </section>
  </main>
</template>
