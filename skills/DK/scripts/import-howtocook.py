#!/usr/bin/env python3
"""HowToCook → DK raw/recipes 格式转换器
用法: python3 scripts/import-howtocook.py <HowToCook路径> [--dry-run] [--date=YYYY-MM-DD]
增量导入：只补 raw/recipes 里缺的菜；已存在的不覆盖（raw 层不可变）。
"""
import os, re, sys, shutil, glob

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(SKILL_DIR, 'raw', 'recipes')
DATE = '2026-08-02'
for _a in sys.argv[1:]:
    if _a.startswith('--date='):
        DATE = _a.split('=', 1)[1]

# HowToCook 分类 → DK 菜品类型 / 烹饪方式
CATEGORY_MAP = {
    'aquatic':        ('水产', '蒸/炖/煎'),
    'breakfast':      ('早餐', '煎/蒸/煮'),
    'condiment':      ('调料', '熬制/发酵'),
    'dessert':        ('甜品', '烤/蒸/煮'),
    'drink':          ('饮品', '煮/冲泡'),
    'meat_dish':      ('荤菜', '炒/炖/红烧'),
    'semi-finished':  ('半成品', '预处理'),
    'soup':           ('汤品', '炖煮'),
    'staple':         ('主食', '蒸/煮/烙'),
    'vegetable_dish': ('素菜', '炒/凉拌'),
}

def parse_md(path):
    """解析 HowToCook 菜谱，返回结构化 dict"""
    with open(path, encoding='utf-8') as f:
        content = f.read()
    
    result = {'path': path}
    # 标题
    m = re.search(r'^#\s+(.+?)$', content, re.M)
    result['title'] = m.group(1).strip() if m else os.path.basename(os.path.dirname(path))
    
    # 难度
    m = re.search(r'预估烹饪难度[：:]\s*([★☆]+)', content)
    result['difficulty'] = len(m.group(1).replace('☆','')) if m else ''
    result['difficulty_stars'] = m.group(1) if m else ''
    
    # 卡路里
    m = re.search(r'预估卡路里[：:]\s*([\d.]+)\s*大卡', content)
    result['calories'] = m.group(1) if m else ''
    
    # 时间（从简介提取 "备菜 X 分钟，烹饪 Y 分钟，总共约 Z 分钟"）
    m = re.search(r'总共约?\s*(\d+)\s*分钟', content)
    result['time'] = m.group(1) if m else ''
    m2 = re.search(r'备菜\s*(\d+)\s*分钟.*?烹饪\s*(\d+)\s*分钟', content)
    result['prep_time'] = m2.group(1) if m2 else ''
    result['cook_time'] = m2.group(2) if m2 else ''
    
    # 原料（## 必备原料和工具 到 ## 计算）
    m = re.search(r'## 必备原料和工具\n(.*?)(?=\n## |\Z)', content, re.S)
    result['ingredients'] = [l.strip().lstrip('+-* ').strip() for l in m.group(1).split('\n') if l.strip() and (l.strip().startswith(('+', '-', '*'))) and not l.strip().startswith(('--', '**'))] if m else []
    
    # 用量（## 计算 到 ## 操作）
    m = re.search(r'## 计算\n(.*?)(?=\n## |\Z)', content, re.S)
    result['quantities'] = [l.strip().lstrip('+-* ').strip() for l in m.group(1).split('\n') if l.strip() and (l.strip().startswith(('+', '-', '*'))) and not l.strip().startswith(('--', '**'))] if m else []
    
    # 步骤（## 操作 到 ## 附加内容/## 参考资料）
    m = re.search(r'## 操作\n(.*?)(?=\n## |\Z)', content, re.S)
    if m:
        steps = []
        for line in m.group(1).split('\n'):
            line = line.strip()
            # 跳过空行和纯标题
            if not line or line.startswith('#') or line.startswith('<!--'):
                continue
            if re.match(r'^\d+[\.、\)]?\s*', line):
                steps.append(re.sub(r'^\d+[\.、\)]?\s*', '', line))
            elif line and not line.startswith(('![', '<', '```')):
                steps.append(line)
        result['steps'] = steps
    else:
        result['steps'] = []
    
    # 附加内容
    m = re.search(r'## 附加内容\n(.*?)(?=\n## |\Z)', content, re.S)
    result['tips'] = [l.strip().lstrip('+-* ').strip() for l in m.group(1).split('\n') if l.strip() and (l.strip().startswith(('+', '-', '*'))) and not l.strip().startswith(('--', '**'))] if m else []
    
    # 参考资料
    m = re.search(r'## 参考资料\n(.*?)(?=\n## |\Z)', content, re.S)
    result['refs'] = [l.strip().lstrip('+-* ').strip() for l in m.group(1).split('\n') if l.strip() and (l.strip().startswith(('+', '-', '*'))) and not l.strip().startswith(('--', '**'))] if m else []
    
    return result

def save_raw(recipe, category, dry_run=False):
    """存为 DK raw/recipes/2026-08-02-菜名.md"""
    safe = re.sub(r'[\\/:*?"<>|\s]+', '', recipe['title'])[:40]
    path = os.path.join(RAW_DIR, f'{DATE}-{safe}.md')
    if os.path.exists(path):
        return None
    
    dish_type, method = CATEGORY_MAP.get(category, ('其他', '其他'))
    
    lines = [f'# {recipe["title"]}', '']
    lines.append('## 来源')
    lines.append('HowToCook（程序员做饭指南，GitHub 10万星）')
    lines.append('')
    lines.append('## 来源网址')
    lines.append(f'https://github.com/Anduin2017/HowToCook（{recipe["path"].replace(chr(92), "/")}）')
    lines.append('')
    lines.append('## 基本信息')
    lines.append(f'- 菜品类型：{dish_type}')
    lines.append(f'- 烹饪方式：{method}')
    if recipe['difficulty_stars']:
        lines.append(f'- 难度：{recipe["difficulty_stars"]}（{recipe["difficulty"]}/5）')
    if recipe['time']:
        lines.append(f'- 时间：约 {recipe["time"]} 分钟' + (f'（备菜{recipe["prep_time"]}分钟 + 烹饪{recipe["cook_time"]}分钟）' if recipe['prep_time'] else ''))
    if recipe['calories']:
        lines.append(f'- 卡路里：约 {recipe["calories"]} 大卡/份')
    lines.append(f'- 采集时间：{DATE}')
    lines.append('')
    lines.append('## 食材')
    for ing in recipe['ingredients']:
        lines.append(f'- {ing}')
    lines.append('')
    if recipe['quantities']:
        lines.append('## 用量（每份）')
        for q in recipe['quantities']:
            lines.append(f'- {q}')
        lines.append('')
    lines.append('## 步骤')
    for i, s in enumerate(recipe['steps'], 1):
        lines.append(f'{i}. {s}')
    lines.append('')
    if recipe['tips']:
        lines.append('## 小贴士')
        for t in recipe['tips']:
            lines.append(f'- {t}')
        lines.append('')
    if recipe['refs']:
        lines.append('## 参考资料')
        for r in recipe['refs']:
            lines.append(f'- {r}')
        lines.append('')
    lines.append('## 科学原理')
    lines.append('（待因子模型编译）')
    lines.append('')
    lines.append('## 安全边界')
    lines.append('（待编译时补充）')
    lines.append('')
    
    if dry_run:
        return path
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path

def existing_names():
    """DK 已有菜谱名（raw + wiki）"""
    names = set()
    for d in (RAW_DIR,):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith('.md'):
                n = f[:-3]
                n = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', n)   # 去掉日期前缀，否则去重失效
                names.add(n)
    return names

def main():
    src = sys.argv[1] if len(sys.argv) > 1 else '/tmp/howtocook'
    dry_run = '--dry-run' in sys.argv
    
    existing = existing_names()
    saved, skipped, failed = [], [], []
    stats = {}
    
    for path in sorted(glob.glob(os.path.join(src, 'dishes', '*', '*.md'))):
        # 跳过子目录嵌套的（如 农家一碗香/农家一碗香.md 在 meat_dish/ 下二级）
        # glob 只匹配一级，嵌套的需额外处理
        pass
    
    # 递归找所有菜谱（含二级目录）
    files = []
    for root, dirs, fnames in os.walk(os.path.join(src, 'dishes')):
        for fn in fnames:
            if fn.endswith('.md') and 'template' not in root:
                files.append(os.path.join(root, fn))
    
    for path in sorted(files):
        category = os.path.basename(os.path.dirname(os.path.dirname(path))) if os.path.dirname(os.path.dirname(path)) != os.path.join(src, 'dishes') else os.path.basename(os.path.dirname(path))
        # 修正 category：dishes/meat_dish/农家一碗香/农家一碗香.md → meat_dish
        rel = os.path.relpath(path, os.path.join(src, 'dishes'))
        category = rel.split(os.sep)[0]
        
        recipe = parse_md(path)
        # 去重：去掉"的做法"后缀，用核心菜名比较
        core = recipe['title']
        for suffix in ('的做法', '（半成品加工）', '（全流程）'):
            core = core.replace(suffix, '')
        core = core.strip()
        dup = False
        for ex in existing:
            ex_core = ex
            for suffix in ('的做法', '（半成品加工）', '（全流程）'):
                ex_core = ex_core.replace(suffix, '')
            ex_core = ex_core.strip()
            # 完全相等 → 重复
            if core == ex_core:
                dup = True
                break
            # 现有名 >= 3 字且是核心名的子串，且核心名剩余部分 < 2 字 → 重复
            # （红烧肉的做法→剩0字→杀；徽派红烧肉→剩"徽派"2字→保留）
            if len(ex_core) >= 3 and ex_core in core:
                remainder = core.replace(ex_core, '').strip()
                if len(remainder) < 2:
                    dup = True
                    break
            # 核心名 >= 3 字且是现有名的子串 → 重复
            if len(core) >= 3 and core in ex_core:
                dup = True
                break
        if dup:
            skipped.append(recipe['title'])
            continue
        if not recipe['steps']:
            failed.append(recipe['title'])
            continue
        
        out = save_raw(recipe, category, dry_run)
        if out:
            saved.append(recipe['title'])
            stats[category] = stats.get(category, 0) + 1
        else:
            skipped.append(recipe['title'])
    
    print(f"=== 转换完成: 保存 {len(saved)} / 跳过 {len(skipped)} / 失败 {len(failed)} ===")
    print(f"分类分布: {stats}")
    if skipped:
        print(f"跳过（去重/已存在）: {skipped[:20]}{'...' if len(skipped)>20 else ''}")
    if failed:
        print(f"失败（无步骤）: {failed[:10]}")

if __name__ == '__main__':
    main()
