# GitHub 知识库体系调研报告

## 调研范围
- Wiki 知识库系统
- LLM 知识库系统
- 知识图谱系统
- 个人知识管理系统

---

## 一、主流知识库模式

### 1. Karpathy LLM Wiki 模式（最流行）

**提出者**：Andrej Karpathy（前 OpenAI/Tesla AI 负责人）

**核心理念**：LLM 自动从原始资料构建结构化 Wiki

**特点**：
- 输入：原始文档、笔记、文章
- 处理：LLM 提取概念、建立链接
- 输出：结构化、互联的 Wiki

**代表项目**：

| 项目 | Stars | 特点 |
|------|-------|------|
| claude-obsidian | 6034 | Obsidian + Claude Code |
| llm-wiki-skill | 1778 | Agent Skill 版本 |
| obsidian-wiki | 1712 | Obsidian 框架 |
| llm-wiki-compiler | 1443 | 知识编译器 |
| karpathy-llm-wiki | 990 | 原版实现 |
| llm-wiki-skill | 571 | OpenClaw/Codex 版本 |

---

### 2. 传统 Wiki 模式

**特点**：手动编辑、Markdown 文件、版本控制

**代表项目**：

| 项目 | Stars | 特点 |
|------|-------|------|
| AFFiNE | 69066 | 下一代知识库 |
| outline | 38756 | 团队知识库 |
| Trilium | 36320 | 个人知识库 |
| MrDoc | 3216 | 中文文档系统 |

---

### 3. 知识图谱模式

**特点**：图结构存储、关系建模、语义搜索

**代表项目**：

| 项目 | Stars | 特点 |
|------|-------|------|
| codebase-memory-mcp | 2956 | 代码知识图谱 |
| graph-memory | 497 | OpenClaw 记忆插件 |
| unigraph-dev | 763 | 通用知识图谱 |
| Thoth | 1223 | 个人 AI 知识图谱 |

---

### 4. RAG 模式

**特点**：检索增强生成、向量数据库、语义搜索

**代表项目**：

| 项目 | Stars | 特点 |
|------|-------|------|
| WeKnora | 15978 | 腾讯 LLM 知识平台 |
| llm_wiki | 10412 | LLM Wiki 桌面应用 |
| arkon | 940 | 企业知识中心 |

---

## 二、最适合我们的方案分析

### 我们的需求

1. 烹饪知识库（原理+食谱+营养）
2. 沟通话术库
3. 可被 Agent 调用
4. 本地存储、轻量级
5. 支持结构化查询

### 方案对比

| 方案 | 优点 | 缺点 | 适合度 |
|------|------|------|--------|
| 当前 SQLite | 轻量、快速 | 手动维护 | ★★★★☆ |
| Karpathy Wiki | 自动构建 | 需要 LLM | ★★★★★ |
| 知识图谱 | 关系建模 | 复杂度高 | ★★★☆☆ |
| RAG | 语义搜索 | 需要向量库 | ★★★☆☆ |
| 传统 Wiki | 简单易用 | 手动编辑 | ★★☆☆☆ |

---

## 三、推荐方案：Karpathy Wiki + SQLite 混合架构

### 设计思路

1. **底层存储**：SQLite（当前方案）
2. **知识构建**：Karpathy Wiki 模式
3. **查询方式**：SQL + 语义搜索

### 优势

- 保留当前 SQLite 的轻量和快速
- 引入 Karpathy Wiki 的自动构建能力
- 支持 Agent 调用
- 可扩展性强

### 实现步骤

1. 定义知识模板（已有）
2. 创建知识提取规则
3. 实现自动构建脚本
4. 集成到 Agent 系统

---

## 四、Karpathy Wiki 核心模式

### 输入
- 原始文档（Markdown、文本）
- 笔记、文章
- 食谱、菜谱

### 处理
1. **概念提取**：从文档中提取关键概念
2. **关系建立**：建立概念之间的链接
3. **结构化**：组织成 Wiki 格式
4. **索引**：创建可搜索的索引

### 输出
- 结构化 Wiki
- 概念图谱
- 可查询的知识库

---

## 五、具体实现建议

### 1. 保留当前 SQLite 架构

- cooking-knowledge.db（烹饪原理）
- dishes-v2.db（菜品食谱）
- nutrition-v2.db（营养化学）

### 2. 添加 Wiki 层

- 概念提取：从食谱中提取烹饪概念
- 关系建立：建立食材-做法-营养关系
- 索引：创建可搜索的索引

### 3. 集成到 Agent

- 用户提问 → 查询 Wiki → 返回答案
- 支持模糊查询
- 支持关联查询

---

## 六、参考项目详解

### 1. claude-obsidian (6034★)

**链接**：github.com/AgriciDaniel/claude-obsidian

**特点**：
- 基于 Karpathy LLM Wiki 模式
- 支持 Obsidian
- 自动构建知识图谱
- 支持 Claude Code

### 2. llm-wiki-skill (1778★)

**链接**：github.com/sdyckjq-lab/llm-wiki-skill

**特点**：
- Agent Skill 版本
- 支持多平台
- 基于 Karpathy 方法论

### 3. WeKnora (15978★)

**链接**：github.com/Tencent/WeKnora

**特点**：
- 腾讯开源
- RAG + Wiki
- 自动维护知识库

### 4. AFFiNE (69066★)

**链接**：github.com/toeverything/AFFiNE

**特点**：
- 下一代知识库
- 支持协作
- 隐私优先

---

## 七、总结

### 当前状态

- SQLite 架构运行良好
- 数据结构清晰
- 查询速度快

### 优化方向

1. 引入 Karpathy Wiki 模式
2. 实现自动知识构建
3. 增强语义搜索能力

### 推荐方案

- 保留 SQLite 作为底层存储
- 添加 Wiki 层作为知识组织
- 集成到 Agent 系统

---

## 八、下一步行动

### 短期（当前）

- 保留 SQLite 架构
- 完善数据内容
- 优化查询脚本

### 中期（可选）

- 引入 Karpathy Wiki 模式
- 实现自动知识构建
- 添加语义搜索

### 长期（探索）

- 知识图谱集成
- 多模态支持
- 协作功能
