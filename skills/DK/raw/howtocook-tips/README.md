# HowToCook tips 语料（18 篇）

> **不可变原始语料**，逐字复制自上游 `tips/` 目录（仅去掉图片引用）。注解与编译产物在 `wiki/`。

| 项目 | 内容 |
|------|------|
| 仓库 | https://github.com/Anduin2017/HowToCook（程序员做饭指南） |
| 许可证 | **Unlicense（公共领域）**，可自由复制/修改/商用 |
| 采集时间 | 2026-09-13 |
| 采集方式 | codeload tarball（master），取 `tips/` 全部 md |
| 上游 tips 结构 | `tips/learn/` 11 篇 · `tips/advanced/` 4 篇 · `tips/` 3 篇 |

## 编译去向

| 语料 | 编译到 |
|------|--------|
| 食品安全 | `wiki/concepts/家庭食品安全.md` |
| 去腥 | `wiki/techniques/去腥.md` |
| 油温判断技巧 | `wiki/techniques/油温判断.md` + `wiki/techniques/火候.md`（补充） |
| 糖色的炒制 | `wiki/techniques/糖色炒制.md` |
| 学习炒与煎 / 辅料技巧 | `wiki/techniques/炒.md`（实操补充） |
| 学习焯水 / 学习腌 / 学习凉拌 / 学习煮 / 学习蒸 | 对应同名技法页（实操补充） |
| 微波炉 / 空气炸锅 / 高压力锅 | `wiki/appliances/微波炉使用.md`、`空气炸锅使用.md`、`高压锅使用.md` |
| **未编译**：高级专业术语、厨房准备、如何洗碗、如何选择现在吃什么 | 只存本目录，用 `grep -r 关键词 raw/howtocook-tips/` 查 |

## 与菜谱语料的关系
`raw/recipes/2026-08-02-*.做法.md` 与 `raw/recipes/2026-09-13-*.做法.md` 是同一仓库的 `dishes/` 目录（HowToCook 共 369 道菜，DK 已收 368，缺 `示例菜` 模板与 `炒青菜`（DK 有自己的 [[炒青菜]]））。
重新导入：`python3 scripts/import-howtocook.py <上游路径> --date=YYYY-MM-DD`
