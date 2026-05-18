# PPT 备注转中文讲解视频

把 PPTX 的每页演讲者备注读出来，自动生成逐页配音视频。

## 单个文件

```bash
python3 ppt_to_video.py "你的文件.pptx" --target-minutes 40
```

输出：

- `你的文件.mp4`
- `你的文件_build/`：中间产物，包含导出的幻灯片图片和每页音频

## 批量处理

```bash
for f in *.pptx; do
  python3 ppt_to_video.py "$f" --target-minutes 40
done
```

## 当前规则

- 逐页提取备注并朗读
- 默认中文女声：`zh-CN-XiaoxiaoNeural`
- 默认语速：`-5%`
- 如果指定 `--target-minutes 40`，会在每页末尾均匀补足停顿，把总时长拉到接近 40 分钟
- 如果某页没有备注，当前会读出“本页暂无备注。”

## 备注

真正的 PPTX 通常至少是几十 KB，常见会有几 MB。  
如果文件只有几百字节，很可能是 Office 的临时文件，不是正式课件。

## 项目结构

```text
frontend/   Vue 3 前端
backend/    Flask 后端与视频处理脚本
backend/storage/  上传文件、任务产物等运行时数据
```

## 后端

```bash
python3 backend/app.py
```

## 前端

```bash
cd frontend
npm install
npm run dev
```

然后打开 Vite 提示的本地地址。前端会把 `/api` 请求代理到 `http://127.0.0.1:5050`。

当前支持：

- 上传 PPTX 并分析页数、备注字数
- 从可用中文音色中选择配音
- 输入自定义试听文本并即时试听
- 选择语速和目标时长
- 在网页里触发生成并下载视频
