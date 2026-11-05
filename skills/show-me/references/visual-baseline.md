# L3/L4 视觉基线与验证

一套可以直接抄的纸墨体系，和五个真实踩过的坑。出自 2026-10-30 的 KVMem 讲解页（一次「不够精美」打回后重做）。

## 纸墨体系

冷白蓝紫的科技风看多了就廉价。纸墨底色 + 一个低饱和强调色，比任何渐变都稳。

```css
:root{
  --paper:#f9f8f5;      /* 页面底 */
  --paper-2:#f4f2ed;    /* 卡片/代码块底 */
  --ink:#1f1e1c;        /* 正文 */
  --ink-2:#3c3a35;      /* 次级正文 */
  --ink-3:#8f8e86;      /* 注释、表头、脚注 */
  --rule:#dbdad3;       /* 分隔线 */
  --rule-soft:#e8e6df;  /* 更淡的分隔线、卡片描边 */

  --accent:#9a5b2c;         /* 赭石：全页唯一强调色 */
  --accent-soft:#f3e7db;
  --accent-line:#d9b995;
}
```

**强调色只落在一个语义上**。多语义就给每一档一个低饱和矿物色，别都用同一个蓝：

| 语义档 | 主色 | 浅底 | 描边 |
|---|---|---|---|
| 热 / 快 / 当前 | `#9a5b2c` 赭石 | `#f3e7db` | `#d9b995` |
| 温 / 中间层 | `#3f5a73` 石板蓝 | `#e9eef2` | `#b4c3d0` |
| 冷 / 可选 / 兜底 | `#4f6450` 苔绿 | `#eaeee8` | `#bac5b6` |

字体分三档，各有分工：

```css
--sans:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
--serif:Georgia,"Songti SC","Noto Serif CJK SC","Source Han Serif SC",serif;
--mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"PingFang SC","Microsoft YaHei",monospace;
```

标题用衬线，正文用无衬线，数字和代码用等宽。**不要外链网络字体** —— 拔网线也得一样。

## 排版数值

| 项 | 值 | 理由 |
|---|---|---|
| 容器 | `max-width:800px` + 左右 40px padding → 内容 720px | 1280 屏上不空，1440 也不散 |
| 正文 | 18px / 行高 1.85 / `max-width:35em` | 每行约 36 汉字，长文不累 |
| H1 | `clamp(30px,4.8vw,45px)` / 行高 1.2 / 字距 -0.022em | 大标题要收紧字距才不散 |
| H2 | 26px / `margin-top:78px`（移动 62px） | 段间呼吸靠上边距，不靠空 div |
| 小字 | 11.5–12px，颜色 `--ink-3` | 脚注、表头、署名 |
| 数字 | `font-variant-numeric:tabular-nums` | 换数字时不跳动 |
| 纸纹 | `feTurbulence` SVG data-URI，`opacity:.03`，`mix-blend-mode:multiply` | 有质感但看不见 |

H2 前面加一道 26px 宽、2px 高的强调色短线，比 emoji 或序号高级。

## 五个坑（都真踩过）

**1. 全局 `p{max-width:35em}` 会截断 flex 装饰线。**
页眉的小字 + 一条延伸横线、署名行 + 上边框，这两个都是 `display:flex` 的 `<p>`，被 35em 限住后线只画到 400px，右边大片空白。
→ 给这类 `<p>` 显式加 `max-width:none`。`width:100%` 不管用，max-width 优先。

**2. 等宽字体栈里没有中文字体，中文会渲染成空白。**
`--mono` 只列了英文等宽，中文字符 fallback 失败。表现是元素盒子和背景都在，字一个不见（headless 截图里尤其明显，用像素扫描才能发现）。
→ 两件事都做：字体栈末尾补 `"PingFang SC","Microsoft YaHei"`；中文一律用 sans，mono 只留给纯数字和代码。

**3. `--virtual-time-budget` 下 CSS 过渡停中间帧。**
用无头浏览器截图验证时，`transition` 和 `animation` 会卡在半途，看到半透明色块、数字错位，误判成 bug。
→ 看静态终态时加 `--force-prefers-reduced-motion`。判断动画是否正常，只能靠真机或 CDP。

**4. IntersectionObserver 在部分环境不触发，内容永久隐身。**
`.rise{opacity:0}` 靠观察器加 `.in`，观察器不动 → 整页白屏。
→ 必须加超时兜底：`setTimeout(() => document.querySelectorAll('.rise:not(.in)').forEach(e=>e.classList.add('in')), 1400)`。

**5. `table-layout:fixed` 的列宽百分比，在移动端 `display:block` 后仍然生效。**
桌面端给列设了 `width:27%`，移动端把 `table/tr/td` 全改 `display:block` 转卡片，那 27% 还在 —— 文字被挤成两三行。
→ 移动端断点里显式重置：`.tbl td{width:auto!important}`。

## 验证清单

交付前跑一遍，全部是确定性检查，不靠眼睛猜：

```bash
# 1. 无横向溢出（三档宽度都要过）
#    在页面里注入：document.title = de.scrollWidth + '/' + de.clientWidth
chrome --headless --window-size=390,900 --dump-dom page.html | grep -o 'P[0-9]::[^<]*'

# 2. JS 语法
python3 -c "import re;s=open('p.html').read();open('/tmp/c.js','w').write(re.findall(r'<script>(.*?)</script>',s,re.S)[-1])"
node --check /tmp/c.js

# 3. 标签平衡（div/section/table/aside）
# 4. 外链清单：只该有正文引用的几个，不能有 CDN / 字体 / 图片
```

看图用 resvg，比 cairosvg 好装：

```bash
node -e "const{Resvg}=require('@resvg/resvg-js');const fs=require('fs');
const r=new Resvg(fs.readFileSync('a.svg','utf8'),{fitTo:{mode:'width',value:1120},font:{loadSystemFonts:true}});
fs.writeFileSync('/tmp/a.png',r.render().asPng())"
```

## 双端审查（硬要求）

390px 和 1280px 都要看，不能只验桌面。移动端最容易坏的三处：表格、演示台的横向布局、代码块长串。断点用 600px。
