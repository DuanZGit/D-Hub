# skill-search

<p align="center"><a href="./README.en.md">English</a> | <strong>中文</strong></p>

<p align="center"><img src="https://raw.githubusercontent.com/DuanZGit/D-Hub/master/docs/covers/skill-search.png" alt="skill-search cover" width="880"></p>

<p align="center"><strong>技能目录不必常驻系统提示，留一个查询入口就够</strong><br><sub>按需检索 · 只返回路径 · 不自动注入</sub></p>

<p align="center">
<a href="https://www.npmjs.com/package/@duanz/pi-skill-search"><img src="https://img.shields.io/npm/v/@duanz%2Fpi-skill-search.svg?style=flat-square" alt="npm"></a>
<a href="https://github.com/DuanZGit/D-Hub/blob/master/LICENSE"><img src="https://img.shields.io/npm/l/@duanz%2Fpi-skill-search.svg?style=flat-square" alt="license"></a>
<a href="https://github.com/DuanZGit/D-Hub"><img src="https://img.shields.io/badge/GitHub-DuanZGit%2FD--Hub-181717?style=flat-square&logo=github" alt="GitHub"></a>
<img src="https://img.shields.io/badge/pi-extension-34d399?style=flat-square" alt="pi extension">
</p>

<p align="center">
<code>pi install npm:@duanz/pi-skill-search</code>
</p>

## 它解决什么

pi 的技能目录常驻系统提示。本机 82 个技能全部摊开约 21,164 字符（≈6,500 tokens），**每一轮都在烧**，不管这次用不用得上。

两个现成解法都不合适：

1. 把低频技能设成 `disable-model-invocation` —— 省了 token，但模型**完全看不见**它们，除非用户记得打 `/skill:名字`
2. 把技能索引全量注入每轮上下文 —— 省下的 token 原样花回去

本扩展补的是这条缝：技能目录不必常驻，**只要查询入口常驻**。一个工具 schema 约 120 tokens/轮。

## 用法

模型调用 `skill_search`：

| 参数 | 说明 |
| --- | --- |
| `query` | 任务描述或关键词；省略则列出全部技能名 |
| `limit` | 返回条数，默认 8 |

返回 `name` / `description` / SKILL.md 绝对路径。模型拿到路径后用 `read` 读正文再决定，所以路径是必返回字段。

## 三条设计约束

1. **只给路径，不给正文**。论文 SkillRouter 在 80K 候选上实测：只暴露 name + description 会让路由准确率掉 37–44 个百分点，必须 body-aware。
2. **不自动注入**。在 `before_agent_start` 塞提示等于把省下的 token 花回去；工具躺在工具列表里就够。
3. **不碰 frontmatter**。扩展只占 extensions 目录，`uipro update` / `npx impeccable update` 不会覆盖它。

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PI_AGENT_DIR` | `~/.pi/agent` | 技能根目录 |
| `DESC_MAX` | `200` | 描述截断长度 |

## 与 ask-me 技能的关系

`ask-me` 是给人的入口（显式 `/skill:ask-me`），`skill_search` 是给模型的入口。装了本扩展后，`ask-me` 的扫描脚本可以退居备用（Minis / DSH 等没有本扩展的环境仍用它）。

## License

MIT © DuanZ
