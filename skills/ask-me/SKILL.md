---
name: ask-me
disable-model-invocation: true
description: >-
  不知道该用哪个技能时来问它 —— 把当前要做的事丢进去，离线索引按关键词打分，
  只回 1–2 个技能名 + SKILL.md 绝对路径，不出清单、不做目录。
---

# ask-me

一件事对应一个技能就够了。这个技能只干一件事：把你现在要干的事对到一两个技能上。

不打字面匹配——先 `route.py` 算分，再在候选里挑。**候选外的技能不许自己另起一个**，那是路由失败，要重写 query。

## 1. 跑一次

```bash
python3 <skill-base-dir>/scripts/route.py "<你现在要做的事，原话>"
```

原话直接丢进去，别翻译成技能术语。用户说「这破玩意儿跑不起来」就传这句，
不要改写成「故障诊断与排查」——索引里存的就是人话。

默认出 1 条，多给几条用 `--top 3`。想看懂为什么用它加 `--explain`：

```bash
python3 <skill-base-dir>/scripts/route.py "帮我看看这段代码为啥这么写" --top 3 --explain
```

## 2. 挑，别列

拿到结果只看前两条，然后：

- **第 1 条分数 ≥ 第 2 条 2 倍** → 只报第 1 条，别把第二名也说出来
- **两条接近** → 一起报，各一句话说明差在哪（用户自己选）
- **都没命中**（全部接近 0）→ 说实话「没有对口技能，我直接做」，然后直接做

输出就三行：技能名、路径、为什么是它。不要三档清单、不要「Primary/Supporting/Optional」，
不要贴分数，不要说「另外还有一些相关技能」。用户要的是答案不是菜单。

## 3. 什么时候别用

- 用户已经点名技能 → 直接用，别路由
- 任务一眼看穿只有一条路（改个错字、查个文件）→ 直接做
- 自己知道该用哪个 → 用，别绕一圈求确认

路由是给「拿不准」用的，不是给每件事套的流程。

## 4. 索引过期时重建

技能增删、改描述、改触发词之后：

```bash
python3 <skill-base-dir>/scripts/build_index.py
```

扫的是 `~/.pi/agent/skills`、`~/.agents/skills`、`~/.pi/agent/npm/node_modules/*/skills`、
`~/.pi/agent/extensions/*/skills`、项目级 `.pi/skills` 等 8 个根。索引存
`scripts/index.json`（121 个技能约 267KB），`--check-index` 能报出没登记进
`~/.agents/skills/INDEX.md` 的用户级技能。

## 5. 触发词表

`scripts/triggers.json` 是人写的补充表，键是技能名、值是**用户真会说的那句话**。
自动切词切不出「复盘」「挂单」「看不懂」这类口语，靠这张表补。

加词的标准：用户会说出这句话，但不会报技能名。加之前先跑
`route.py "<你想的那句话>" --explain`，看是不是已经有别的技能在抢这个说法。

## 6. 显式/自动的台账

`scripts/apply_modes.py` 按 `KEEP_AUTO` 名单统一改各技能 frontmatter 的
`disable-model-invocation`：在名单里就删掉（变自动，模型能看见），不在就加上（变显式，省上下文）。

```bash
python3 <skill-base-dir>/scripts/apply_modes.py --check   # 只看差异
python3 <skill-base-dir>/scripts/apply_modes.py --apply   # 真改盘
bash <skill-base-dir>/scripts/selftest.sh                 # 17 条断言
```

**ask-me 自己不在名单里**（2026-11-21 用户要求关闭自动触发），别把它加回去。

## 7. 改完要回灌

真源在 `~/projects/D-Hub/skills/ask-me`，pi 读的是
`~/.config/magpie/library/skills/ask-me` 的软链。改完真源必须：

```bash
cp -a ~/projects/D-Hub/skills/ask-me/. ~/.config/magpie/library/skills/ask-me/
```

再更新 `~/.agents/skills/.sources.json` 里该技能的 `local_hash`（`sha256(SKILL.md)[:16]`），
然后 commit + push。只改真源不回灌 = 改动不生效。
