<div align="center">

# PPT to Video

### 将 PowerPoint 备注自动转换为中文讲解视频

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5+-42B883?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-8+-646CFF?style=flat-square&logo=vite&logoColor=white)](https://vite.dev/)
[![Flask](https://img.shields.io/badge/Flask-3.1+-000000?style=flat-square&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4+-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-7+-007808?style=flat-square&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![LibreOffice](https://img.shields.io/badge/LibreOffice-26+-18A303?style=flat-square&logo=libreoffice&logoColor=white)](https://www.libreoffice.org/)

</div>

`PPT to Video` 是一个面向中文培训课件的自动化工具：读取 `.pptx` 中每一页的演讲者备注，将其转换为中文语音，并按页合成为讲解视频。  
它适合批量处理培训材料、课程课件、档案数字化说明等“页面内容已准备好，只差配音与成片”的场景。

## 功能特性

- 自动提取每页 PPT 备注
- 清理备注中的页码、日期等噪音文本
- 支持中文语音选择与试听
- 支持设置语速与目标时长
- 自动导出幻灯片画面并合成为 MP4
- 支持 WebUI 操作与命令行批量处理
- 前后端分离，便于继续扩展任务队列、页面预览与逐页编辑

## 技术栈

| 层级 | 技术 |
| --- | --- |
| Frontend | Vue 3、Vite、Tailwind CSS、Lucide Vue |
| Backend | Python、Flask |
| Speech | edge-tts |
| Rendering | LibreOffice、FFmpeg、pdftoppm |
| Architecture | 前后端分离、本地任务处理 |

## 项目结构

```text
.
├── frontend/              # Vue 3 前端
├── backend/               # Flask API 与视频处理逻辑
│   ├── app.py
│   ├── ppt_to_video.py
│   └── storage/           # 上传文件、任务产物等运行时数据
├── README.md
└── .gitignore
```

## 工作流程

```text
PPTX
  ↓
提取演讲者备注
  ↓
中文语音合成
  ↓
导出幻灯片画面
  ↓
按页合成视频
  ↓
MP4
```

## 快速开始

### 1. 启动后端

```bash
python3 backend/app.py
```

默认运行在：

```text
http://127.0.0.1:5050
```

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

然后打开 Vite 输出的本地地址。前端会将 `/api` 请求代理到后端服务。

## 命令行用法

### 单个文件

```bash
python3 backend/ppt_to_video.py "你的文件.pptx" --target-minutes 40
```

输出：

- `你的文件.mp4`
- `你的文件_build/`：中间产物，包含导出的幻灯片图片和每页音频

### 批量处理

```bash
for f in *.pptx; do
  python3 backend/ppt_to_video.py "$f" --target-minutes 40
done
```

## 当前规则

- 默认中文音色：`zh-CN-XiaoxiaoNeural`
- 默认语速：`-5%`
- 指定 `--target-minutes` 后，会通过页尾停顿将整体时长拉近目标值
- 如果某页没有备注，当前会使用占位语音：`本页暂无备注。`

## 运行环境

建议安装：

- Python 3.10+
- Node.js 20+
- FFmpeg
- LibreOffice
- `pdftoppm`

Python 依赖示例：

```bash
pip install flask edge-tts mutagen
```

## 适用场景

- 培训课件自动配音
- 企业内训视频批量生产
- 档案、政务、教育类知识内容转视频
- 已有 PPT 与讲稿，但缺少讲师录音的项目

## 注意事项

- 真正的 `.pptx` 文件通常至少是几十 KB，常见会有几 MB；如果文件只有几百字节，很可能是 Office 临时文件
- 当前版本更适合“静态页 + 备注讲解”的视频生成；如需保留复杂动画与转场，需要进一步扩展导出策略

## Roadmap

- [ ] 接入真实前端上传与任务状态
- [ ] 增加每页备注预览与逐页编辑
- [ ] 增加 PPT 页面预览
- [ ] 支持批量任务队列
- [ ] 支持更多中文音色与 SSML 配置

