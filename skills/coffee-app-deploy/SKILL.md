---
name: coffee-app-deploy
description: coffee.duanz.xin:1218 咖啡工坊（Atelier）PWA 的部署方式与页面结构。用户提到「部署咖啡」「coffee.duanz.xin」「咖啡工坊上线」时使用。
---

# coffee.duanz.xin · Atelier 咖啡工坊

## 结构（2026-11-07 起）
- 入口 `/` = `index.html`：选「意式 / 手冲」两条线（键盘 1/2 快捷），工作目录 `/home/duanz/workspace/咖啡咖啡/index.html`
- `/atelier_espresso_3007z_bricks_01s.html`：意式线（3007Z × Bricks 01S，选杯型→豆子→参数→实操）
- `/atelier_pourover_donut.html`：手冲线（辛鹿甜甜圈滤杯 × 云南瑰夏 16g，湿纸→三段注水→计时→调参）
- 两子页导航栏最左有「← 入口」回 index

## 部署
- 一条命令：`/home/duanz/workspace/咖啡咖啡/deploy.sh`
- 它做四件事：复制 3 个 html 到 `/var/www/coffee/` → 注入 manifest/SW 头 → 重写 `/var/www/coffee/manifest.json`（name=Atelier）→ SW 版本号刷成 `coffee-v<时间戳>` 并把两个子页加进 SHELL 预缓存
- 验证：脚本自带 6 个路径的 200 检查 + manifest name 打印
- PWA 安装名：**Atelier**（short_name 同）

## 注意
- SW 里 HTML 走 network-first，改版后手机端刷新即可拿到新版；图标 `/var/www/coffee/icons/` 复用旧的一套
- 子页面文件名别改，deploy.sh 与 SW SHELL 都写死了
