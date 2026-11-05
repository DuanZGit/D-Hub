# evidence_url 与 health_warnings 填写规范

> DK 技能 v2 schema 新增的两列。**evidence_url** 是科学依据,**health_warnings** 是不适用人群。
> 两列分开,不让科学依据埋在描述里,也不让健康风险淹没在内容中。

---

## 1. evidence_url(科学依据 URL)

### 1.1 跟 source_url 的区别

| 字段 | 含义 | 例 |
|------|------|-----|
| `source_url` | **页面级内容来源**(小红书/微博/微信/抖音/报纸文章) | `https://www.xiaohongshu.com/discovery/item/abc123` |
| `evidence_url` | **科学依据出处**(PubMed/CNKI/中国食物成分表/食品化学教材/官方指南) | `https://pubmed.ncbi.nlm.nih.gov/12345/` |

⚠️ 两者**不冲突**,一个 DB 记录可以同时有两个 URL:
- source_url 告诉读者"我从哪儿看到这条信息的"
- evidence_url 告诉读者"这条信息的科学根据是啥"

### 1.2 哪些算合格的 evidence_url

| ✅ 合格 | ❌ 不合格 |
|---------|----------|
| PubMed / PMC 论文(`pubmed.ncbi.nlm.nih.gov`, `ncbi.nlm.nih.gov/pmc`) | 知乎答主回答(即使写得专业) |
| CNKI / 万方 / 维普 论文 | 个人博客(除非作者是认证营养师/医生) |
| 中国食物成分表(第 6 版) | 营销文(品牌官网) |
| 中国营养学会指南 | 百度知道 |
| 国家卫健委 / 世卫组织(WHO) 公告 | 维基百科(可作辅助,不作主依据) |
| 食品化学教材(指定章节, ISBN) | Reddit / Quora 帖子 |
| Mayo Clinic / Cleveland Clinic / NHS 医疗指南 | 自媒体公众号(无明确作者资质) |
| Uptodate / Cochrane Library | 美团/大众点评(非医疗内容) |
| ESPEN / ASPEN 临床营养指南 | 商家商品页 |

### 1.3 怎么填

- **优先选有 DOI 的论文**:`https://doi.org/10.1016/j.xxx`
- **多个依据**用 `;` 分隔:`url1;url2;url3`(不超 3 个)
- **教材**:写明章节+页码,在 `description` 里加"《食品化学》第 X 章 第 Y 节"
- **找不到怎么办**:
  1. 留空,**不要伪造 URL**
  2. 在 `description` 或 `health_note` 写"【依据待补】——建议查《xxx》第 X 章"
  3. LLM 主动调用 `ctx_search` 搜"topic + 2024/2025 review"找最新综述

### 1.4 自动补工具

```bash
# 把某条记录的 evidence_url 补上
bash scripts/manage-cooking-db.sh add-method  # 录入时填 evidence_url 字段

# 批量查某类目所有 evidence_url 缺失的记录
sqlite3 db/cooking-knowledge.db \
  "SELECT id, name FROM cooking_methods WHERE evidence_url IS NULL OR evidence_url = '';"

# 让 LLM 帮查(用 ctx_search 找 PubMed 综述)
# 例: 给定 cooking_method.id=5, LLM 查 "Maillard reaction 2024 review"
#   找到后 UPDATE cooking_methods SET evidence_url='...' WHERE id=5;
```

---

## 2. health_warnings(健康警示 / 不适用人群)

### 2.1 写什么

**结构化文本**,用 `,` 或 `;` 分隔多个项目。建议格式:

```
[人群1]:[原因1];[人群2]:[原因2];[场景]:[说明]
```

### 2.2 例子

```sql
-- 高 GI 食物,糖尿病/减脂慎用
health_warnings = '糖尿病患者:GI=85 偏高;减脂期:碳水密度高;空腹食用:易血糖波动'

-- 油煎,高血脂/胆囊疾病慎食
health_warnings = '高血脂患者:饱和脂肪高;胆囊疾病:刺激胆汁分泌;胃溃疡:加重负担'

-- 含麸质,乳糜泻/麸质过敏禁用
health_warnings = '乳糜泻患者:含麸质;麸质过敏:免疫反应;小麦过敏:同源蛋白'

-- 生食,孕妇/老人/小孩禁
health_warnings = '孕妇:李斯特菌风险;老人/小孩:免疫弱;免疫力低下:沙门氏菌'
```

### 2.3 哪些场景**必须**填

| 场景 | 必填字段 | 模板 |
|------|----------|------|
| 烹饪方法 | `health_warnings` | "高 [X] 患者慎用" |
| 调味料 | `health_warnings` | "高血压/肾病:钠含量高" |
| 食材营养 | `health_warnings` | "过敏/不耐受/慢性病" |
| 化学反应 | `health_warnings` | "高温生成物:丙烯酰胺/杂环胺" |
| FAQ | `health_warnings` | "特殊人群注意" |

### 2.4 哪些**不需要**填

- **纯方法论** 的条目(例如"如何切洋葱"无健康风险)
- **已经被普遍接受的安全做法**(例如"洗手"无警告)
- **数据库已经废弃/历史的条目**

### 2.5 怎么查"该警告谁"

```bash
# 用 LLM 主动查:
# "这种食材/烹饪方法对哪些人群有风险? 给出 PubMed/CNKI 链接"

# 模板提示词(可直接给 LLM):
# "作为注册营养师,基于最新(2024-2025)临床证据,
#  说明 <X> 的不适用人群。每条警告引用 1 个权威源。"
```

---

## 3. 完整录入示例

以 `cooking_methods` 表新增一条"煎"为例:

```sql
INSERT INTO cooking_methods (
  name, name_en, principle, temperature, pros, cons, suitable_for, tips,
  health_note,                -- 一般健康提示
  health_warnings,            -- v2 新增
  source_platform, source_title, source_url,        -- 来源
  evidence_url,               -- v2 新增,科学依据
  source_method, source_precision
) VALUES (
  '煎', 'pan-fry',
  '食材表面与高温油脂直接接触,产生美拉德反应和焦糖化',
  '150-180℃',
  '外酥里嫩,香气浓郁',
  '油烟大,易产生丙烯酰胺',
  '薄切肉类/鱼类/蔬菜',
  '热锅凉油,中火,控温',
  '保留蛋白质,维生素流失少',                                    -- health_note
  '高血脂患者:饱和脂肪高;胆囊疾病:刺激胆汁分泌;胃溃疡:加重负担;孕妇:避免反复煎油',  -- health_warnings
  '小红书', '@家庭料理笔记', 'https://www.xiaohongshu.com/...',                  -- source_*
  'https://pubmed.ncbi.nlm.nih.gov/29368945/',  -- 真实 PubMed 链接(美拉德反应+丙烯酰胺)
  'manual', 'page-level'
);
```

### 3.1 录入时必填顺序

1. **基础信息**(name/principle/temperature/...)— 老样子
2. **来源**(source_*)— 老样子
3. **🆕 evidence_url** — 必填,找不到时留空但要标"【依据待补】"
4. **🆕 health_warnings** — 必填,**没有风险也要写"无明显禁忌"**

### 3.2 反例 ❌

```sql
-- 错 1: 写 source_url 当 evidence_url
evidence_url = 'https://www.xiaohongshu.com/abc'  -- 这是 source_url 不是 evidence_url

-- 错 2: 警告只说"少吃"不说为什么
health_warnings = '少吃一点'  -- 太模糊,无操作价值

-- 错 3: 警告用错别字/口语
health_warnings = '胖纸别吃'  -- 不专业,应说"减脂期/肥胖人群"

-- 错 4: 留空 + 假装没事
health_warnings = NULL  -- 默认是"无警告"还是"忘了填"？必须显式写"无明显禁忌"
```

---

## 4. 数据迁移 & 回填

### 4.1 已有 200+ 条记录,如何批量补 evidence_url?

不推荐全自动。**半自动**:
1. `SELECT id, name FROM cooking_methods WHERE evidence_url IS NULL LIMIT 5;` 拿 5 条样本
2. LLM 对每条查 PubMed/教材,生成 evidence_url
3. 人工 review,UPDATE 回 DB
4. 每批 5-10 条,避免给 PubMed API 太大压力

### 4.2 已有的 health_warnings 数据怎么迁移?

- `health_note` 字段如果包含"禁忌"信息,人工 review 后迁移到 `health_warnings`
- 没有"禁忌"信息的保持 `health_warnings = NULL`(但建议补"无明显禁忌")

### 4.3 回填进度跟踪

写一个简单的 view(可选):

```sql
CREATE VIEW IF NOT EXISTS v_evidence_url_missing AS
SELECT 'cooking_methods' AS tbl, id, name FROM cooking_methods WHERE evidence_url IS NULL OR evidence_url = ''
UNION ALL
SELECT 'ingredient_nutrition', id, name FROM ingredient_nutrition WHERE evidence_url IS NULL OR evidence_url = ''
UNION ALL
SELECT 'chemical_reactions', id, name FROM chemical_reactions WHERE evidence_url IS NULL OR evidence_url = ''
-- ... 按需要加
;

-- 查回填进度
SELECT tbl, COUNT(*) AS missing_count FROM v_evidence_url_missing GROUP BY tbl;
```

---

## 5. 参考资源

- **PubMed**: https://pubmed.ncbi.nlm.nih.gov/  (免费,无 key)
- **中国食物成分表** 第 6 版(杨月欣 主编,北京大学医学出版社, ISBN 978-7-5659-1448-7)
- **食品化学** 第 3 版(阚建全 主编,中国农业大学出版社)
- **中国营养学会**: https://www.cnsoc.org/  (DRIs 2023)
- **WHO 营养指南**: https://www.who.int/publications/i?topics=nutrition
- **国家卫健委**: http://www.nhc.gov.cn/
- **ESPEN 临床营养指南**: https://www.espen.org/guidelines-home

---

*规范版本: v2 (2026-06-15)*
*对应 schema migration: db/migrations/v2_*.sql*
*维护: daily-knowledge skill / AGENTS.md*
