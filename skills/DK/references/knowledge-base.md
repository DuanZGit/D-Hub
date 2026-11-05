# DK 知识库管理

> Wiki 页面和 SQLite 数据库的结构、扩展操作。子工作流步骤见 workflows.md，此处只讲知识库本身。

## 目录结构

```
DK/
├── SKILL.md                ← 主文件（触发/分类/工作流入口）
├── RECIPE-GENERATOR.md     ← 食谱生成详细指南
├── references/             ← 按需加载的详解（workflows/frameworks/knowledge-base/examples）
├── docs/                   ← 领域文档（factor-model、confidence-standards、anti-patterns、权威信息源索引等）
├── scripts/                ← 工具脚本（wiki-to-html-v2.py、knowledge-search.sh 等）
├── db/                     ← SQLite 数据库 + schema + migrations
│   ├── cooking-knowledge.db   烹饪原理库（烹饪方式/食材处理/调味料）
│   ├── dishes-v2.db           示例菜品库（详细食谱/多种做法/精确用量）
│   └── nutrition-v2.db        营养化学库（营养成分/化学反应/健康建议）
├── raw/                    ← 原始资料（不可变，按日期命名）
│   ├── recipes/            ← 食谱 md（最大来源：HowToCook 导入 361 个）
│   ├── cooklikehoc/        ← 老乡鸡菜品溯源报告语料（339 条 + README 溯源/许可；图片不入库）
│   ├── howtocook-tips/     ← HowToCook tips/ 语料（18 篇技法/安全/厨具，Unlicense 公共领域）
│   ├── techniques/ nutrition/ chemistry/ ingredients/
│   ├── appliances/         ← 厨具清洁指南
│   ├── first-aid/ stains/ storage/ health/
│   └── misc/               ← 库存/营养档案/晚餐合集模板等家庭文件
└── wiki/                   ← 编译后的知识页面（人类可读）
    ├── recipes/ ingredients/ techniques/ chemistry/ concepts/ nutrition/ appliances/
    ├── laoxiangji/         ← 老乡鸡菜谱编译页（339 条，标题形如「老乡鸡 · 菜名」）+ index.md 总览
    └── index.md / log.md   ← 索引与操作日志
```

> HTML 卡片是**构建产物**，由 `scripts/wiki-to-html-v2.py` 现生成到 `workspace/dk-cards/`，不入版本库（`wiki/*.html` 已加 .gitignore）。

## 数据统计（2026-09-25 快照，时点数据，非活文档）

> 实时计数用：`find wiki -name '*.md' | wc -l` / `find raw -type f | wc -l` / `sqlite3 db/cooking-knowledge.db 'SELECT COUNT(*) FROM source_registry;'`

- Wiki 页面：490 个 md（09-25 合并 3 组跨目录重复页：十字花科蔬菜/氨基酸互补/胶原蛋白水解 归 concepts，laoxiangji 340 / ingredients 49 / recipes 39 / techniques 22 / appliances 15 / chemistry 14 / concepts 3 / nutrition 1；含 2026-09-25 新增《料理实验室》7 页）
- 脚本层：12 个
- raw 资料：795 个文件（recipes 387 含 HowToCook 导入 / cooklikehoc 340 / appliances 20 / howtocook-tips 18 / foodlab 2（中文版因子记录 + 英文版交叉验证与补充）/ 其余 28）
- 数据库：cooking-knowledge（source_registry 6 条登记来源）/ dishes-v2 4 表 200+ 条 / nutrition-v2 6 表 70 条
- 菜谱来源：HowToCook（程序员做饭指南，Unlicense 协议）+ 人工整理 + **CookLikeHOC（老乡鸡菜品溯源报告，无 LICENSE，仅限内部检索/个人参考，禁止外发）**
- 书源因子库：《料理实验室 The Food Lab》（青岛出版社 2021，第 1–9 章）→ `raw/foodlab/2026-09-25-料理实验室-因子记录.md`，已拆卡进 wiki 19 页（详见 index.md）

## 老乡鸡菜谱子库（wiki/laoxiangji/）

- 339 条，标题统一 `老乡鸡 · 菜名`；总览 `wiki/laoxiangji/index.md`
- **复现等级**（判定 + 页面展示）：
  - 🟢 A（72）：全部常见食材，家常可直做
  - 🟡 B（73）：含品牌半成品/复合料，需替代
  - 🔴 C（194）：依赖老乡鸡中央厨房自产预制料或官方未公布配比，只能近似复刻
- 每条页面固定含：复现等级 + 理由 / 需替代的预制料 / 原文配料步骤（逐字）/ 家庭换算（×系数 + 盐油下调提示）/ 因子分析 / 预期成品 / 安全边界 / DK 已有页面交叉链接 / 置信度
- ⚠️ **配方是中央厨房批量口径，不是家庭食谱**：回答菜谱类问题时，若引用这批数据，必须同时给出缩放系数并提示盐、油下调，否则算输出无效（反模式 #1 同族：无来源/失真引用）
- 覆盖检查：查 `wiki/laoxiangji/` 下同名文件；找不到再用 `grep -r 关键词 raw/cooklikehoc/`

## Wiki 页面因子化模板

每条知识按因子维度记录：

**食材页面**：结构因子（细胞壁/纤维密度）、化学因子（pH/水分活度/关键成分）、热力学因子（变性温度/降解阈值）、最佳反应条件、禁忌条件

**烹饪方式页面**：传导介质和温度范围、激活的反应路径、适用/不适用食材因子范围

**调味料页面**：反应窗口（温度-时间曲线）、协同/拮抗效应、降解产物和风险

**食谱页面**：输入（食材因子组合）→ 条件（方式+调味时序）→ 输出（质地/色泽/风味/营养保留率）→ 可复现性验证记录

**生活知识页面**：核心原理、关键因子、可复现步骤、证据来源、置信度、边界条件

## 扩展知识库

### 添加新食谱
1. 创建 `raw/recipes/YYYY-MM-DD-菜名.md`
2. 编译成 `wiki/recipes/菜名.md`
3. 更新索引 `wiki/index.md`、日志 `wiki/log.md`
4. 建立交叉引用（食材、化学反应、营养）

### 添加新食材
1. 创建 `raw/nutrition/YYYY-MM-DD-食材名.md` → 编译 `wiki/ingredients/食材名.md`
2. 更新索引日志；营养成分数据入库

### 添加新概念 / 技巧
1. `raw/chemistry|techniques/YYYY-MM-DD-名称.md` → 编译对应 wiki 子目录
2. 更新索引日志；关联相关食谱和食材；技巧页加温度/时间参数

### 添加厨具清洁指南
1. 创建 `raw/appliances/YYYY-MM-DD-指南名.md`
2. 更新索引日志

### HTML 编译
用 `scripts/wiki-to-html-v2.py`（完整 markdown 解析 + [[wiki链接]] 跳转渲染），不要手写 HTML 或重写脚本。

## 数据更新策略

1. **定期更新**：每季度核对权威机构数据（权威来源清单见 `docs/权威信息源索引.md`）
2. **来源验证**：所有数据标注来源和更新时间
3. **版本控制**：schema 变更走 `db/migrations/`；数据库每月备份

## 常见问题

- **Wiki 和数据库的区别？** Wiki 是给人读的结构化文档；数据库是给程序查的结构化数据。互补使用。
- **冲突信息怎么办？** 优先权威机构数据，标注来源和时间，提供多方观点。
- **知识库会自动更新吗？** 目前手动维护；实测反馈走修订工作流落盘。
