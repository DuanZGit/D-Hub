#!/usr/bin/env python3
"""DK Wiki 页面 → HTML 因子卡片生成器 v2
修复：
- 完整 markdown 子集解析（粗体/斜体/代码/代码块/链接/标题嵌套/有序无序列表）
- 快速信息识别（同时支持 | 表格 和 - 列表 两种格式）
- 代码块渲染（``` 围栏）
- 标签 section 解析（#tag 形式）
- 相关概念/食谱只取 [[wiki 名]]，去掉 - 之后的说明
- 置信度渲染为独立 callout
- 长段落保留完整不截断

用法: python3 scripts/wiki-to-html-v2.py [分类]
"""
import os, re, sys, html

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_DIR = os.path.join(SKILL_DIR, 'wiki')
OUTPUT_DIR = os.path.join(os.environ.get('WORKSPACE') or ('/var/minis/workspace' if os.path.isdir('/var/minis/workspace') else os.path.expanduser('~/workspace')), 'dk-cards')

THEME = {
    'ingredients': {'primary': '#c4452c', 'light': '#fbeeea', 'name': '食材', 'icon': '🥬', 'emoji_h2': {'快速信息': '📋', '核心特性': '💡', '营养成分': '📊', '食用方式': '🍽️', '搭配建议': '🤝', '保存方法': '🗄️', '常见品种': '🌱', '常见问题': '❓', '相关概念': '🔗', '相关食谱': '🍳', '标签': '🏷️', '置信度': '✅'}},
    'chemistry':    {'primary': '#2f5d8a', 'light': '#ecf2f8', 'name': '化学反应', 'icon': '🧪', 'emoji_h2': {'快速信息': '📋', '反应机理': '⚙️', '生成物': '🧬', '感官影响': '👁️', '烹饪应用': '🍳', '健康影响': '⚕️', '相关概念': '🔗', '标签': '🏷️', '置信度': '✅'}},
    'techniques':   {'primary': '#5a7d3a', 'light': '#f1f5ec', 'name': '烹饪技巧', 'icon': '🔪', 'emoji_h2': {'快速信息': '📋', '核心原理': '💡', '关键技巧': '🎯', '油烟与健康': '🏭', '国际炒菜对比': '🌍', '相关概念': '🔗', '标签': '🏷️', '置信度': '✅'}},
    'nutrition':    {'primary': '#a85d8f', 'light': '#f7eef3', 'name': '营养素', 'icon': '💊', 'emoji_h2': {'快速信息': '📋', '核心信息': '💡', '功效': '✨', '来源': '🌾', '相关概念': '🔗', '标签': '🏷️', '置信度': '✅'}},
}

# === Markdown 解析 ===
def md_inline(text):
    """行内 markdown → HTML"""
    # 先转义再处理
    s = html.escape(text)
    # 代码 `xxx` → <code>
    s = re.sub(r'`([^`]+)`', r'<code class="md-code">\1</code>', s)
    # 粗体 **xxx** 或 __xxx__
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', s)
    # 斜体 *xxx* 或 _xxx_（避免和粗体冲突）
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
    # Wiki 链接 [[name]] → 超链接（跳转到对应卡片）
    def wiki_link_to_href(match):
        name = match.group(1)
        # 1. 检查是否在DK wiki中（遍历所有分类）
        wiki_dirs = ['ingredients', 'chemistry', 'techniques', 'nutrition', 'recipes', 'concepts', 'appliances']
        for cat_dir in wiki_dirs:
            wiki_path = os.path.join(WIKI_DIR, cat_dir, f'{name}.md')
            if os.path.exists(wiki_path):
                # 根据分类生成不同的链接
                if cat_dir == 'recipes':
                    return f'<a href="minis://workspace/{name}.html" class="wiki-link">{name}</a>'
                else:
                    return f'<a href="minis://workspace/dk-cards/{cat_dir}-{name}.html" class="wiki-link">{name}</a>'
        # 2. 检查raw食谱
        raw_patterns = [
            f'2026-08-02-{name}-DK.md',
            f'{name}.md',
            f'{name}-DK.md',
        ]
        for pattern in raw_patterns:
            raw_path = os.path.join(SKILL_DIR, 'raw/recipes', pattern)
            if os.path.exists(raw_path):
                return f'<a href="minis://workspace/{name}.html" class="wiki-link">{name}</a>'
        # 3. 默认：搜索关键词
        return f'<a href="javascript:void(0)" class="wiki-link" onclick="alert(\'搜索: {name}\')">{name}</a>'
    
    s = re.sub(r'\[\[([^\]]+)\]\]', wiki_link_to_href, s)
    return s

def is_table_block(lines, i):
    """从第 i 行开始判断是否是表格块（含表头、分隔、数据行）"""
    if i >= len(lines) or not lines[i].startswith('|'):
        return False
    if i + 1 >= len(lines) or '---' not in lines[i+1]:
        return False
    if not lines[i+1].startswith('|'):
        return False
    return True

def parse_table(lines, i):
    """从第 i 行开始解析表格"""
    rows = []
    while i < len(lines) and lines[i].startswith('|'):
        cells = [c.strip() for c in lines[i].strip('|').split('|')]
        rows.append(cells)
        i += 1
    # 第一行是表头，第二行是分隔（---），第三行开始是数据
    if len(rows) >= 2 and all(set(c.replace('-', '').strip()) <= set('') for c in rows[1]):
        header = rows[0]
        data = rows[2:]
    else:
        header = []
        data = rows
    return header, data, i

def is_code_block(lines, i):
    """判断是否是代码块开始"""
    return i < len(lines) and lines[i].startswith('```')

def parse_code_block(lines, i):
    """解析代码块"""
    code_lines = []
    # 跳过开始的 ```
    lang = lines[i][3:].strip()
    i += 1
    safety = 0
    while i < len(lines) and not lines[i].startswith('```') and safety < 10000:
        code_lines.append(lines[i])
        i += 1
        safety += 1
    if i < len(lines):
        i += 1  # 跳过结束的 ```
    return lang, '\n'.join(code_lines), i

def parse_page(content):
    """完整 markdown 解析"""
    lines = content.split('\n')
    i = 0
    
    title = ''
    intro = ''
    sections = []  # 每个 section 是 dict: {title, blocks: [...]}
    current_section = None
    in_code = False
    code_buffer = []
    code_lang = ''
    
    # 跳过 frontmatter（如有）
    if lines and lines[0].strip() == '---':
        while i < len(lines) and lines[i].strip() != '---':
            i += 1
        if i < len(lines):
            i += 1  # 跳过第二个 ---
    
    # 解析标题
    if i < len(lines) and lines[i].startswith('# '):
        title = lines[i][2:].strip()
        i += 1
        # 引言
        if i < len(lines) and lines[i].startswith('>'):
            intro_lines = []
            while i < len(lines) and lines[i].startswith('>'):
                intro_lines.append(lines[i].lstrip('> ').strip())
                i += 1
            intro = ' '.join(intro_lines)
    
    last_i = -1
    while i < len(lines):
        if i == last_i:
            i += 1
            continue
        last_i = i
        line = lines[i]
        
        # 二级标题
        if line.startswith('## '):
            if current_section:
                sections.append(current_section)
            current_section = {'title': line[3:].strip(), 'blocks': []}
            i += 1
            continue
        
        # 在某个 section 内
        if current_section is None:
            i += 1
            continue
        
        # 代码块
        if is_code_block(lines, i):
            lang, code, i = parse_code_block(lines, i)
            current_section['blocks'].append({'type': 'code', 'lang': lang, 'content': code})
            continue
        
        # 表格
        if is_table_block(lines, i):
            header, data, i = parse_table(lines, i)
            current_section['blocks'].append({'type': 'table', 'header': header, 'data': data})
            continue
        
        # 三级标题
        if line.startswith('### '):
            current_section['blocks'].append({'type': 'h3', 'text': line[4:].strip()})
            i += 1
            continue
        
        # 无序列表
        if re.match(r'^[\-\*\+]\s', line):
            items = []
            while i < len(lines) and re.match(r'^[\-\*\+]\s', lines[i]):
                items.append(re.sub(r'^[\-\*\+]\s+', '', lines[i]).strip())
                i += 1
            current_section['blocks'].append({'type': 'ul', 'items': items})
            continue
        
        # 有序列表
        if re.match(r'^\d+\.\s', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s', lines[i]):
                items.append(re.sub(r'^\d+\.\s+', '', lines[i]).strip())
                i += 1
            current_section['blocks'].append({'type': 'ol', 'items': items})
            continue
        
        # 空行
        if not line.strip():
            i += 1
            continue
        
        # 普通段落（合并相邻非空行）
        para_lines = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '```', '-', '* ', '+ ', '>')):
            para_lines.append(lines[i].strip())
            i += 1
        # 强制至少推进
        if i < len(lines) and lines[i].startswith(('**', '*')) and not lines[i].startswith(('* ', '+ ')):
            # 粗体行不在 para 累积里，但会被本分支捕获 → 强制跳过
            if not para_lines:
                current_section['blocks'].append({'type': 'p', 'text': lines[i].strip()})
                i += 1
            else:
                current_section['blocks'].append({'type': 'p', 'text': ' '.join(para_lines)})
                para_lines = []
        elif para_lines:
            current_section['blocks'].append({'type': 'p', 'text': ' '.join(para_lines)})
    
    if current_section:
        sections.append(current_section)
    
    return {'title': title, 'intro': intro, 'sections': sections}

# === HTML 渲染 ===
BASE_CSS = """
:root {
  --primary: __PRIMARY__;
  --light: __LIGHT__;
  --bg: #fafaf7;
  --card: #ffffff;
  --text: #2a2a2a;
  --muted: #6e6e6e;
  --border: #e8e3da;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.7; padding: 2rem 1rem;
}
.container { max-width: 780px; margin: 0 auto; }
.header {
  text-align: center; padding: 1.5rem 0; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem;
}
.header h1 {
  font-size: 2rem; font-weight: 700; color: var(--primary); margin-bottom: 0.25rem;
}
.header .subtitle { color: var(--muted); font-size: 0.9rem; }
.header .intro {
  margin-top: 0.75rem; color: var(--text); font-size: 0.95rem; font-style: italic;
  max-width: 600px; margin-left: auto; margin-right: auto;
}
.section {
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 1.25rem 1.5rem; margin-bottom: 1rem;
}
.section h2 {
  font-size: 1.1rem; font-weight: 700; color: var(--primary); margin-bottom: 0.75rem;
  padding-bottom: 0.4rem; border-bottom: 2px solid var(--light);
}
.section h3 {
  font-size: 0.95rem; font-weight: 600; color: var(--primary); margin: 0.75rem 0 0.4rem;
}
.section p { margin: 0.5rem 0; font-size: 0.95rem; }
.section p + p { margin-top: 0.3rem; }

/* 快速信息卡片网格（横排） */
.quick-info-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.6rem;
}
.quick-info-grid .item {
  text-align: center; padding: 0.5rem; background: var(--light); border-radius: 6px;
}
.quick-info-grid .label {
  font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em;
}
.quick-info-grid .value { font-weight: 600; margin-top: 0.2rem; font-size: 0.95rem; }

/* 表格 */
table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.9rem; }
th, td {
  padding: 0.5rem 0.6rem; text-align: left; border-bottom: 1px solid var(--border);
}
th { background: var(--light); color: var(--primary); font-weight: 600; }
tr:hover td { background: #faf8f4; }

/* 列表 */
ul, ol { padding-left: 1.5rem; margin: 0.5rem 0; }
ul li, ol li { padding: 0.25rem 0; font-size: 0.95rem; }
ul.plain { list-style: none; padding-left: 0; }

/* 代码块 */
pre.md-codeblock {
  background: #1e1e1e; color: #e8e8e8; padding: 1rem 1.25rem; border-radius: 6px;
  margin: 0.6rem 0; overflow-x: auto; font-family: "SF Mono", Consolas, monospace;
  font-size: 0.85rem; line-height: 1.5;
}

/* 行内代码/粗体/斜体/Wiki引用 */
.md-code {
  background: #f5f3ee; color: #c4452c; padding: 1px 5px; border-radius: 3px;
  font-family: "SF Mono", Consolas, monospace; font-size: 0.88em;
}
.wiki-ref {
  background: var(--light); color: var(--primary); padding: 1px 6px; border-radius: 3px;
  font-size: 0.88em; font-weight: 500;
}

/* 置信度 callout */
.confidence-box {
  background: linear-gradient(135deg, var(--light) 0%, #ffffff 100%);
  border-left: 4px solid var(--primary);
  padding: 1rem 1.25rem; border-radius: 6px; margin: 0.5rem 0;
}
.confidence-box .level {
  display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px;
  font-size: 0.85rem; font-weight: 700; margin-right: 0.5rem;
}
.confidence-box .level.high { background: #5a7d3a; color: white; }
.confidence-box .level.mid { background: #d4a017; color: white; }
.confidence-box .level.low { background: #c4452c; color: white; }
.confidence-box .reason { color: var(--muted); font-size: 0.9rem; margin-top: 0.3rem; }

/* 标签 */
.tag-list { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.tag-list .tag {
  background: var(--light); color: var(--primary); padding: 0.25rem 0.7rem;
  border-radius: 4px; font-size: 0.85rem;
}

/* wiki 链接气泡 */
.wiki-link {
  display: inline-block;
  background: var(--light);
  color: var(--primary);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.85rem;
  text-decoration: none;
  margin: 0.1rem;
  transition: all 0.2s;
}
.wiki-link:hover {
  background: var(--primary);
  color: white;
}
.related-cloud { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.related-cloud .item {
  background: var(--light); color: var(--primary); padding: 0.4rem 0.8rem;
  border-radius: 4px; font-size: 0.9rem; font-weight: 500;
}

/* 底部 */
.back-link { text-align: center; margin-top: 2rem; font-size: 0.9rem; }
.back-link a { color: var(--primary); text-decoration: none; }
footer { text-align: center; color: var(--muted); font-size: 0.8rem; padding: 1.5rem 0 0.5rem; }
"""

def render_table(header, data):
    if not header and not data:
        return ''
    rows_html = ['<table>']
    if header:
        rows_html.append('<thead><tr>')
        for cell in header:
            rows_html.append(f'<th>{md_inline(cell)}</th>')
        rows_html.append('</tr></thead>')
    if data:
        rows_html.append('<tbody>')
        for row in data:
            rows_html.append('<tr>')
            for cell in row:
                rows_html.append(f'<td>{md_inline(cell)}</td>')
            rows_html.append('</tr>')
        rows_html.append('</tbody>')
    rows_html.append('</table>')
    return ''.join(rows_html)

def render_block(block):
    t = block['type']
    if t == 'p':
        text = block['text']
        # 如果段落全是 ` - ` 列表项（如 "标签" 后），转为标签
        if text.startswith('#'):
            tags = re.findall(r'#(\S+)', text)
            if tags and len(tags) >= 2:
                return '<div class="tag-list">' + ''.join(f'<span class="tag">#{md_inline(tag)}</span>' for tag in tags) + '</div>'
        return f'<p>{md_inline(text)}</p>'
    elif t == 'ul':
        items = ''.join(f'<li>{md_inline(item)}</li>' for item in block['items'])
        return f'<ul>{items}</ul>'
    elif t == 'ol':
        items = ''.join(f'<li>{md_inline(item)}</li>' for item in block['items'])
        return f'<ol>{items}</ol>'
    elif t == 'table':
        return render_table(block['header'], block['data'])
    elif t == 'code':
        lang = block.get('lang', '')
        content = html.escape(block['content'])
        return f'<pre class="md-codeblock" data-lang="{lang}">{content}</pre>'
    elif t == 'h3':
        return f'<h3>{md_inline(block["text"])}</h3>'
    return ''

def render_section(section, theme):
    title = section['title']
    # emoji 前缀
    h2_emoji = theme.get('emoji_h2', {}).get(title, '')
    title_html = f'{h2_emoji} {title}' if h2_emoji else title
    
    # 特殊处理：快速信息
    if title == '快速信息':
        blocks_html = ''
        items_html = []
        for block in section['blocks']:
            if block['type'] == 'p':
                # 把 "分类：食材" 拆成 label/value
                m = re.match(r'^([^：:]+)[：:]\s*(.+)$', block['text'])
                if m:
                    items_html.append(f'<div class="item"><div class="label">{md_inline(m.group(1))}</div><div class="value">{md_inline(m.group(2))}</div></div>')
                    continue
            elif block['type'] == 'ul':
                for item in block['items']:
                    m = re.match(r'^([^：:]+)[：:]\s*(.+)$', item)
                    if m:
                        items_html.append(f'<div class="item"><div class="label">{md_inline(m.group(1))}</div><div class="value">{md_inline(m.group(2))}</div></div>')
                        continue
                    # 不匹配 key:value 的 ul 项，作为段落渲染
                    blocks_html += render_block({'type': 'p', 'text': item})
                continue
            elif block['type'] == 'table':
                # 表格形式（如 美拉德反应 "项目|内容"）
                header, data = block['header'], block['data']
                for row in data:
                    if len(row) >= 2:
                        items_html.append(f'<div class="item"><div class="label">{md_inline(row[0])}</div><div class="value">{md_inline(row[1])}</div></div>')
                continue
            # 其他类型用通用渲染
            blocks_html += render_block(block)
        if items_html:
            return f'<div class="section"><h2>{title_html}</h2><div class="quick-info-grid">{"".join(items_html)}</div>{blocks_html}</div>'
    
    # 特殊处理：置信度
    if title == '置信度':
        level = '低'
        reason = '依据较少'
        for block in section['blocks']:
            if block['type'] == 'ul':
                for item in block['items']:
                    m = re.match(r'\*\*级别\*\*[：:]\s*(.+)', item)
                    if m: level = m.group(1).strip('*').strip()
                    m = re.match(r'\*\*依据\*\*[：:]\s*(.+)', item)
                    if m: reason = m.group(1).strip('*').strip()
            elif block['type'] == 'p':
                m = re.search(r'级别[：:]\s*\*?\*?(.+?)\*?\*?\n', block['text'])
                if m: level = m.group(1).strip().rstrip(',').strip()
                m = re.search(r'依据[：:]\s*(.+?)(?:\n|$)', block['text'])
                if m: reason = m.group(1).strip()
        level_class = 'low'
        if '高' in level: level_class = 'high'
        elif '中' in level: level_class = 'mid'
        return f'''<div class="section"><h2>✅ 置信度</h2>
<div class="confidence-box">
  <span class="level {level_class}">{md_inline(level)}</span>
  <span class="reason">{md_inline(reason)}</span>
</div></div>'''
    
    # 特殊处理：标签
    if title == '标签':
        tags = []
        for block in section['blocks']:
            if block['type'] == 'ul':
                for item in block['items']:
                    tags.extend(re.findall(r'#(\S+)', item))
            elif block['type'] == 'p':
                tags.extend(re.findall(r'#(\S+)', block['text']))
        if tags:
            tags_html = ''.join(f'<span class="tag">#{md_inline(tag)}</span>' for tag in tags)
            return f'<div class="section"><h2>{title_html}</h2><div class="tag-list">{tags_html}</div></div>'
        return ''
    
    # 特殊处理：相关概念/食谱
    if title in ('相关概念', '相关食谱'):
        items = []
        for block in section['blocks']:
            if block['type'] == 'ul':
                for item in block['items']:
                    # 提取 [[wiki 名]]，去掉 - 之后的说明
                    m = re.match(r'\[([^\]]+)\]', item)
                    if m:
                        name = m.group(1)
                        items.append(name)
            elif block['type'] == 'p':
                items.extend(re.findall(r'\[\[([^\]]+)\]\]', block['text']))
        if items:
            items_html = ''.join(f'<span class="item">[[{md_inline(name)}]]</span>' for name in items)
            return f'<div class="section"><h2>{title_html}</h2><div class="related-cloud">{items_html}</div></div>'
        # 如果没有内容，尝试从所有 section 提取（兜底）
        return ''
    
    # 普通 section
    blocks_html = ''.join(render_block(b) for b in section['blocks'])
    if not blocks_html.strip():
        return ''
    return f'<div class="section"><h2>{title_html}</h2>{blocks_html}</div>'

def render_page(category, content):
    theme = THEME.get(category, THEME['ingredients'])
    parsed = parse_page(content)
    
    sections_html = ''.join(render_section(s, theme) for s in parsed['sections'])
    
    css = BASE_CSS.replace('__PRIMARY__', theme['primary']).replace('__LIGHT__', theme['light'])
    
    title_safe = html.escape(parsed['title'])
    intro_safe = html.escape(parsed['intro']) if parsed['intro'] else ''
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_safe} — DK {theme["name"]}</title>
<style>{css}</style>
</head>
<body>
<div class="container">
  <header class="header">
    <h1>{theme["icon"]} {title_safe}</h1>
    <p class="subtitle">DK {theme["name"]} · Wiki 因子卡片</p>
    {f'<p class="intro">{intro_safe}</p>' if intro_safe else ''}
  </header>
  
  {sections_html}
  
  <div class="back-link">
    <a href="minis://workspace/dk-cards/index.html">← 返回 DK 卡片目录</a>
  </div>
  
  <footer>
    <p>DK · {theme["name"]}卡片 · 基于 Wiki 自动渲染 · 2026-08-02</p>
  </footer>
</div>
</body>
</html>
'''

def render_index(pages):
    """渲染卡片目录"""
    items = []
    for cat, files in pages.items():
        theme = THEME[cat]
        items.append(f'<div class="card-section"><h2>{theme["icon"]} {theme["name"]} ({len(files)})</h2>')
        items.append('<div class="grid">')
        for fname, title in sorted(files, key=lambda x: x[1]):
            items.append(f'<a href="{fname}.html" class="card"><div class="card-title">{html.escape(title)}</div></a>')
        items.append('</div></div>')
    
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DK Wiki 因子卡片目录</title>
<style>
:root {{ --bg:#fafaf7; --card:#fff; --text:#2a2a2a; --muted:#6e6e6e; --border:#e8e3da; --primary:#c4452c; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); line-height:1.6; padding:2rem 1rem; }}
.container {{ max-width:900px; margin:0 auto; }}
h1 {{ text-align:center; color:var(--primary); margin-bottom:2rem; }}
.card-section {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:1.5rem; margin-bottom:1.5rem; }}
.card-section h2 {{ font-size:1.2rem; margin-bottom:1rem; color:var(--text); padding-bottom:0.5rem; border-bottom:2px solid var(--border); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:0.75rem; }}
.card {{ display:block; background:#fafaf7; border:1px solid var(--border); border-radius:6px; padding:0.75rem; text-decoration:none; color:var(--text); transition:all 0.2s; }}
.card:hover {{ background:var(--primary); color:white; border-color:var(--primary); }}
.card-title {{ font-size:0.9rem; font-weight:500; }}
footer {{ text-align:center; color:var(--muted); font-size:0.8rem; padding:1.5rem 0 0.5rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>📚 DK Wiki 因子卡片目录</h1>
  {"".join(items)}
  <footer>
    <p>DK · 因子模型 · 2026-08-02 · 点击卡片查看详情</p>
  </footer>
</div>
</body>
</html>'''

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    categories = ['ingredients', 'chemistry', 'techniques', 'nutrition']
    if len(sys.argv) > 1 and sys.argv[1] in categories:
        categories = [sys.argv[1]]
    
    pages = {cat: [] for cat in categories}
    
    for cat in categories:
        cat_dir = os.path.join(WIKI_DIR, cat)
        if not os.path.isdir(cat_dir):
            continue
        
        for fname in sorted(os.listdir(cat_dir)):
            if not fname.endswith('.md') or fname in ('index.md', 'log.md'):
                continue
            if fname.startswith('appliances-cleaning') or fname.startswith('confidence-pending'):
                continue
            
            name = fname[:-3]
            content = open(os.path.join(cat_dir, fname), encoding='utf-8').read()
            html_content = render_page(cat, content)
            
            out_path = os.path.join(OUTPUT_DIR, f'{cat}-{name}.html')
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            parsed = parse_page(content)
            pages[cat].append((cat + '-' + name, parsed['title'] or name))
    
    index_html = render_index(pages)
    with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html)
    
    total = sum(len(v) for v in pages.values())
    print(f'=== 生成完成: {total} 个页面 ===')
    for cat, files in pages.items():
        print(f'  {THEME[cat]["name"]}: {len(files)}')

if __name__ == '__main__':
    main()