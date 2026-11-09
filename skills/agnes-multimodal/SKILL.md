---
disable-model-invocation: true
name: agnes-multimodal
description: 用 Agnes 供应商生成图片或视频时用这份路由。触发：生成图片/画一张/文生图/图生图/生成视频/图生视频/Agnes 出图出片。图像走 pi 官方 codemode `models.generateImages`（Agnes 供应商，扩展 agnes-media 已注册，免费期）；视频走 CLI `~/.pi/agent/bin/agnes-video`（pi 无 video 模型类型，任务走 Agnes 异步 API）。不要试图用 chat 模型或 pi-multix（provider 矩阵固定，接不了 Agnes）来出图出片。
---

# Agnes 多模态（图像 + 视频）

## 图像（pi 原生入口，优先）

扩展 `~/.pi/agent/extensions/agnes-media` 把 `Agnes/agnes-image-2.5-flash` 注册进 image 模型目录。
任何会话的 codemode 里直接调（默认已开 `+codemode`）：

```js
const painter = await models.getModelOfType("image", "Agnes", "agnes-image-2.5-flash");
const result = await models.generateImages(painter, {
  input: [
    { type: "text", text: "一只在沙发上打盹的橘猫，水彩风格，1K" },
    // 图生图/多参考帧：加 { type: "image", data: "<base64>", mimeType: "image/png" }
  ],
});
if (result.stopReason === "error") { console.log(result.errorMessage); }
for (const block of result.output) {
  if (block.type === "image") image(block); // 结果名会带临时文件路径
}
```

- 出图尺寸档位：改扩展里 `model.extraParams.size`（1K/2K/3K/4K），不传默认 1K
- key 自动走 `~/.agents-env/get-key.sh PI_AGNES_API_KEY`（和 models.json 的 Agnes chat 同源）
- 当前免费期；定价 1K/2K/3K/4K 档 ¥70/100/140/160 每千张

## 视频（CLI，走限时免费模型）

pi 的模型目录没有 video 类型，视频走 CLI。CLI 固定用 `agnes-video-2.5-flash`：**限时免费 ¥0/秒，仅 720P**（付费版 agnes-video-2.5 不碰；用户要求只用免费通道）。建任务→轮询→下载 mp4：

```sh
~/.pi/agent/bin/agnes-video "海浪拍打礁石，低角度慢镜头" \
  --seconds 5 --size 720P --aspect 16:9 --out ~/Videos
# 图生视频：加 --i2i <首帧URL>（可配 --i2i-end <尾帧URL>）
# 参考模式：--ref <图/音频/视频URL> 可多次；--v2v <视频URL>（可配 --audio）
# 成功 stdout 一行本地 mp4 路径；--json 输出 {video_id, path}
```

- 时长 4–12s；免费 flash 仅 720P（传其它档位 CLI 直接报错）
- 队列满时服务端返 503 `video_queue_full`，稍后重试即可，不是配置问题
- 长任务：生成要几分钟，用 `bg_run` 跑，别用同步 bash 卡住
- 轮询文档：`GET https://api.agnes-ai.cn/agnesapi?video_id=X&model_name=agnes-video-2.5-flash`

## 出片后

- 图片/视频结果路径打给用户（可点链接，绝对路径）
- 免费期间视频也不用为花钱确认，图像同样免费
- 生图模型 `agnes-image-2.5-flash` 免费期；`agnes-3.0-flash` 是纯对话模型，不出图不出片
- **`agnes-3.0-flash` 能看图，但必须走 `/v1/chat/completions`（api 类型 `openai-completions`）**：`/v1/responses` 和 `/v1/messages` 两个入口的图片转换是坏的，带图必 400（2026-10-09 实测，报错里图片变成 `{'type':'unknown'}`）；models.json + agnes-media 扩展里该模型的 api 已固定为 `openai-completions`，**改回去就会复爆**
