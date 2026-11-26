# webshare

把 pi 会话或任意文件变成公网临时链接。内置 `/share` 走 GitHub gist / Radius，本机没有 `gh` CLI 时用不了；这个扩展走自建的 `share.duanz.xin`，不限文件大小。

## 用法

- `/webshare` — 分享当前会话（JSONL 转成可读的深色 HTML，工具调用可展开）
- `/webshare <文件路径>` — 原样分享任意文件（图片/PDF/压缩包等）
- `/webshare --list` — 列出所有还没删的分享
- `/webshare --rm <token>` — 删掉某个分享（token 或完整链接都行）

## 依赖

需要本机已经装好 `~/.pi/agent/bin/share` 脚本，并且 `share.duanz.xin` 的公网入口已配置。
