#!/usr/bin/env node
/**
 * route.mjs — 内容形状 → 模板/技能的本地路由
 *
 * 给一句内容描述（或几个关键词），输出候选模板与理由。纯本地关键词打分，不联网、不调模型。
 * 模型可以自己读 templates/ROUTING.md 判断，也可以先跑本脚本拿候选再拍板。
 *
 * 用法：
 *   node scripts/route.mjs "讲一下 TCP 三次握手的过程"
 *   node scripts/route.mjs "我们三个方案的优缺点对比"
 *   node scripts/route.mjs --json "占位"
 *
 * 输出：推荐 1 个 + 备选 2 个，每个带一句「为什么」和「怎么套」。
 * 退出码 0；描述太短（<4 字）时退出码 2 并提示补一句。
 */
const ROUTES = [
  {
    id: "interactive-scenes",
    file: "templates/interactive-scenes.html",
    title: "交互情景库 · 13 组可玩可演",
    fit: ["互动", "交互", "试试", "拖", "点", "演示", "情景", "模拟", "操作", "玩", "手感", "实验", "调节", "空间", "视差", "隧道"],
    why: "要人动手才往下走：能拖、能点、能演一段过程、能看远近层次",
    how: "读文件头「四类场景」表 → 复制一个 S[id] 的四件套（init/update/pointer/param）",
  },
  {
    id: "motion-16",
    file: "templates/motion-16.html",
    title: "Three.js 动效库 · 16 组",
    fit: ["动效", "背景", "粒子", "流体", "星空", "主视觉", "氛围", "动画背景", "呼吸", "波动"],
    why: "只要一个自己动的背景，不需要人参与",
    how: "点选预览 → 复制那组的核心代码到你的页面",
  },
  {
    id: "skeleton-tech",
    file: "templates/skeleton-tech.html",
    title: "讲法骨架 · 终端仪表盘",
    fit: ["参数", "配置", "清单", "规格", "终端", "命令行", "指标", "监控", "API", "报错", "接口文档"],
    why: "参数/规格/状态这类结构化清单，用状态条 + 编号导轨最清楚",
    how: "复制到产出目录 → 只改数据区与文案，保留栅格与动效层",
  },
  {
    id: "skeleton-ink",
    file: "templates/skeleton-ink.html",
    title: "讲法骨架 · 书页",
    fit: ["概念", "原理", "为什么", "疏解", "观点", "短文", "讲清楚", "理解", "本质", "逻辑", "讲一下", "过程", "怎么回事", "机制"],
    why: "要讲一个概念而不是摆数据，竖排书脊 + 正文缩进让人肯读",
    how: "复制 → 换标题、正文与引用，保留排版节奏",
  },
  {
    id: "skeleton-mag",
    file: "templates/skeleton-mag.html",
    title: "讲法骨架 · 杂志封面",
    fit: ["介绍", "发布", "报告", "产品", "年度", "总结", "亮点", "封面", "宣传"],
    why: "视觉冲击优先的介绍/报告，首字下沉 + 三栏 + 色块",
    how: "复制 → 换封面标题与三栏内容",
  },
  {
    id: "skeleton-zen",
    file: "templates/skeleton-zen.html",
    title: "讲法骨架 · 留白卷",
    fit: ["一句话", "情绪", "留白", "极简", "感悟", "观点", "安静", "诗"],
    why: "只有一句话或一个观点时，留白比信息密度更有力",
    how: "复制 → 只换那一句与署名",
  },
  {
    id: "showcase-board",
    file: "templates/showcase-board.html",
    title: "展示台 · 方块榜",
    fit: ["排名", "排行", "倍数", "占比", "对比", "谁多", "榜单", "Top"],
    why: "已定结论的排名/倍数，方块数即数值最直观",
    how: "复制 → 改数据数组与基准线",
  },
  {
    id: "showcase-narrative",
    file: "templates/showcase-narrative.html",
    title: "展示台 · 叙事",
    fit: ["经过", "历程", "时间线", "因果", "故事", "演变", "复盘", "怎么走到"],
    why: "有因果或时间顺序，时间轴播放 + 每幕重放",
    how: "复制 → 按幕填事件与动画",
  },
  {
    id: "showcase-dashboard",
    file: "templates/showcase-dashboard.html",
    title: "展示台 · 仪表盘",
    fit: ["参数", "滑杆", "调参", "如果", "假设", "模型", "模拟结果", "敏感度"],
    why: "有参数可调、结果跟着变，滑杆最直接",
    how: "复制 → 接上你的计算函数",
  },
  {
    id: "showcase-topology",
    file: "templates/showcase-topology.html",
    title: "展示台 · 拓扑",
    fit: ["架构", "链路", "依赖", "服务", "调用", "节点", "网络", "请求走", "怎么走", "走一遍", "拓扑"],
    why: "谁连着谁、节点细节多，点节点出详情 + 请求沿链走",
    how: "复制 → 改节点与边",
  },
  {
    id: "minicharts",
    skill: true,
    weight: 1.6,
    title: "minicharts 技能（不是模板）",
    fit: ["数字", "占比", "饼图", "漏斗", "预算", "花费", "统计", "分布", "增长"],
    why: "一组数字要画成主题里的实物，手绘、按比例、可点",
    how: "走 minicharts 技能自己的工作流（先 --examples 看范例）",
  },
  {
    id: "decision-deck",
    weight: 1.6,
    file: "~/.pi/agent/templates/decision-deck-template.html",
    title: "决策台",
    fit: ["选哪个", "方案", "决策", "拍板", "取舍", "选项", "要不要"],
    why: "要用户勾选/复制指令，卡片多选 + 实时拼提示词",
    how: "复制模板 → 只改 initialItemsData",
  },
];

const NEG = {
  "interactive-scenes": ["不要交互", "静态", "别动"],
};

const args = process.argv.slice(2);
const jsonOut = args.includes("--json");
const text = args.filter((a) => a !== "--json").join(" ").trim();

if (text.length < 4) {
  console.error("route: 描述太短（<4 字），补一句内容形状再来，例如「讲一下三次握手的过程」。");
  process.exit(2);
}

const scored = ROUTES.map((r) => {
  let score = 0;
  const hits = [];
  const w = r.weight || 1;
  for (const k of r.fit) if (text.includes(k)) { score += 2 * w; hits.push(k); }
  for (const k of NEG[r.id] || []) if (text.includes(k)) { score -= 3; hits.push(`-${k}`); }
  return { ...r, score, hits };
}).sort((a, b) => b.score - a.score);

const strip = (r) => ({ id: r.id, file: r.file || null, skill: !!r.skill, title: r.title, score: r.score, hits: r.hits, why: r.why, how: r.how });

const top = scored.filter((r) => r.score > 0).slice(0, 3);
if (!top.length) {
  const fb = [ROUTES.find((r) => r.id === "skeleton-ink"), ...scored.filter((r) => r.id !== "skeleton-ink").slice(0, 1)];
  if (jsonOut) {
    console.log(JSON.stringify({ query: text, fallback: true, candidates: fb.map(strip) }, null, 2));
  } else {
    console.log(`没有命中明显形状，按「讲清楚」默认走书页：\n  ${fb[0].file}  ${fb[0].title}\n  理由：${fb[0].why}`);
    if (fb[1]) console.log(`备选：${fb[1].title}  (${fb[1].file || "技能"})`);
  }
  process.exit(0);
}


if (jsonOut) {
  console.log(JSON.stringify({ query: text, candidates: top.map(strip) }, null, 2));
} else {
  console.log(`「${text}」→ 推荐 ${top[0].title}`);
  console.log(`  路径：${top[0].file || "（技能，见 SKILL.md）"}`);
  console.log(`  为什么：${top[0].why}`);
  console.log(`  怎么套：${top[0].how}`);
  if (top.length > 1) {
    console.log("备选：");
    for (const r of top.slice(1)) console.log(`  · ${r.title}  (${r.file || "技能"})  命中：${r.hits.join("、")}`);
  }
}
