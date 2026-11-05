# 本机适配（pi @ duanz-ai，Linux 无桌面）

上游 SKILL.md 是写给 Codex 的（依赖「应用内浏览器侧边栏」和 Codex 自带 Python）。本文件记录在本机运行时**替代方案与已改动的部分**。

## 解释器（重要）

- 脚本必须用 `~/pw-venv/bin/python` 运行；系统 `python3` 只有标准库。
- `~/pw-venv` 内含：playwright 1.63（Chromium 在 `~/.cache/ms-playwright/chromium-1243`）、pdfplumber、pypdfium2。

```bash
~/pw-venv/bin/python scripts/build_pdf.py <input.md> <output.pdf> --title "标题"
python3 scripts/build_map.py map_data.json outputs/trip_map.html   # build_map 只用标准库
```

## PDF 导出（Step 9）

- 本机没有 Edge/Chrome。`scripts/build_pdf.py` 已改：**优先用 playwright `page.pdf()`**（已实测通过），Edge/Chromium CLI 仅作兜底。
- 中文已解决：**Noto Sans CJK SC 已装好**（免 sudo：`apt-get download fonts-noto-cjk` → `dpkg-deb -x` → `~/.local/share/fonts/noto-cjk` → `fc-cache -f`）。
  PDF 实测嵌入 `NotoSansCJKsc-Regular/Bold`（装字体前是 `WenQuanYiZenHei`）。
- 页数质检走 pdfplumber，可用。

## PDF 视觉质检（替代 pdftoppm）

本机没有 poppler。改用：

```bash
~/pw-venv/bin/python scripts/pdf_to_png.py <output.pdf> /tmp/qa_page
```

生成 `qa_page_p1.png` 等，然后**看图确认排版**（表格不断行、标题不孤行、无方块字）。

## 交付（Step 11）

- 本机没有 Codex 的 `:codex-file-citation{...}`，直接给绝对路径即可；需要网页预览再用 pi-web。
- 地图与 PDF 都放客户 `outputs/` 目录。

## 浏览器与登录（Step 0 / 3 / 5 / 6）—— 与上游最大差异

- 上游要求「把登录页打开在侧边栏，让客户扫码」，pi 没有侧边栏；本机是**无桌面服务器**（无 DISPLAY、无在跑的 VNC）。
- 可用工具：playwright（可无头、可持久化 profile）、Xvfb + x11vnc（已安装，未启用）、系统 sshd 已开 X11Forwarding。
- **当前选定方案：Cookie 导入（b1.3）**。本机出口与用户家里宽带同一出口 → IP 这一维天然一致，是这套方案能成立的关键前提。
- 取哪两个站：`hotels.ctrip.com`（酒店实价）、`www.dianping.com`（餐厅评分/人均）。
  **高德不需要**（未登录也能查路线/公交）；**飞猪暂不做**（淘宝系风控最严）。
- 流程：用户在自己浏览器登录 → 点「Cookie 与接口抓取器」悬浮球 → Cookie 视图 → 格式切到 **JSON** + 勾「含子域名」→ 复制 → 粘到本机 `~/.secrets/trip_ctrip.json` / `trip_dianping.json`（`umask 077` 写入）。
- 注入与验证：

```bash
~/pw-venv/bin/python scripts/trip_session.py --cookies ~/.secrets/trip_ctrip.json \
    --domain .ctrip.com --url https://hotels.ctrip.com/ --site ctrip --shot /tmp/ctrip.png
```

  会打印 cookie 条数/HTTP 状态/标题，并截图供人工确认是否已登录；profile 持久化在 `~/.cache/trip-planner/profile-<site>`，后续轮次复用。
- **UA 必须与被导出 cookie 的浏览器一致**（`--ua`）；否则平台判定「换了设备」，登录态可能立刻失效。
- 已知风险：大众点评风控最凶，注入后可能立刻要验证码或掉登录；携程先行验证。
- 未登录时的硬约束不变：拿不到真实房价/评分就如实标「待核实」，**不得编造**，也不代下任何单。

## 上游同步

- base commit `9b5a0a1`（2026-08-19）。本机改动：
  - `scripts/build_pdf.py`：PDF 引擎改为优先 playwright；Edge/Chromium CLI 仅兜底。
  - 新增 `scripts/pdf_to_png.py`（取 PDF 页首页图，替代 poppler）。
  - 新增 `scripts/trip_session.py`（把导出的 cookie 注入 Playwright 会话）。
  - `SKILL.md` 顶部加指向本文件的指针。
- `git pull` 时若 SKILL.md / build_pdf.py 冲突，保住上述改动即可。
