#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 CookLikeHOC（老乡鸡菜品溯源报告）语料导入 DK。

用法：
  1) git clone --depth 1 https://github.com/Gar-b-age/CookLikeHOC.git /tmp/cooklikehoc
  2) python3 scripts/import-cooklikehoc.py
产出：
  raw/cooklikehoc/     逐字语料（保留已有 README；图片不入库，见上游仓库）
  wiki/laoxiangji/     339 个「老乡鸡 · 菜名」编译页 + index.md 总览
复现等级判据：老乡鸡自产预制料(配料目录同名/链接) > 老乡鸡中央厨房 > 供应商品牌半成品 > 复合料词 > 官方未公布配比
"""
import os, re, json, shutil, hashlib
from collections import Counter, defaultdict

SRC = '/tmp/cooklikehoc'
DK = '/var/minis/skills/DK'
RAW = os.path.join(DK, 'raw', 'cooklikehoc')
WIKI = os.path.join(DK, 'wiki', 'laoxiangji')
DATE = '2026-09-13'
CATS = ['主食','凉拌','卤菜','早餐','汤','炒菜','炖菜','炸品','烤类','烫菜','煮锅','砂锅菜','蒸菜','配料','饮品']

ING_HEADS = re.compile(r'(配料|原料|食材|用料|材料|主料|辅料|已知成分|配方|成分)')
STEP_HEADS = re.compile(r'(步骤|做法|制作|工艺|流程|烹饪|出品)')

SUPPLIER_HINT = ['圣农','正大','温氏','凤祥','太阳谷','菲诺','卜蜂','杨景','中茂','康喜','冶春','圣恩','嘉吉','双汇','新希望','仙坛','益客','中粮','六和','大成','春雪','凤翔','安井','千味','佳沃','国联','恒都','科尔沁','桃李','清美','蜀海','老乡鸡中央厨房','中央厨房','来自']
HALF_PRODUCT = ['底料','调味酱','调味料','调味汁','酱料','料包','汤料','腌料','裹粉','起酥油','预制','半成品','调理','速冻','冷冻','熟制','拆骨','卤油','味汁','老卤','卤汤','浓汤','骨汤','料理包','调味油','拌菜红油','基料','炸鸡粉','脆炸粉','面包糠','千页豆腐','鱼豆腐','鸡米花','薯饼','洋葱圈']
BRAND_TAIL = re.compile(r'（[^（）]*(?:生物|食品|股份|集团|农牧|实业|冷链|供应链|肉类|肉品|养殖|粮油|水产|乳业|饮品|餐饮|商贸|贸易|产业)[^（）]*）')
PREP_HINT = ['老乡鸡中央厨房', '中央厨房', '老乡鸡自产']
PREP_NAMES = [x[:-3] for x in os.listdir(os.path.join(SRC, '配料')) if x.endswith('.md') and x != 'README.md']
COMMON_COND = set('''盐 糖 白砂糖 冰糖 红糖 生抽 老抽 酱油 味极鲜酱油 蒸鱼豉油 蚝油 醋 陈醋 香醋 白醋 米醋 料酒 黄酒 白酒 香油 芝麻香油 橄榄油 花生油 菜籽油 大豆油 食用油 猪油 熟猪油 鸡油 花椒油 藤椒油 辣椒油 红油 芝麻酱 花生酱 豆瓣酱 郫县豆瓣酱 甜面酱 黄豆酱 番茄酱 辣椒酱 蒜蓉辣酱 沙茶酱 海鲜酱 排骨酱 叉烧酱 蜂蜜 鸡精 味精 胡椒粉 五香粉 十三香 孜然 淀粉 玉米淀粉 生粉 面粉 酵母 泡打粉 小苏打 碱粉 牛奶 淡奶油 炼乳'''.split())

# 分类 → 条件/输出/安全边界（因子模板）
CAT_FACTOR = {
 '炒菜': dict(way='炒（200–300℃，油传导，秒~分钟级）',
   react='美拉德反应（140–165℃）+ 蛋白质表面快速变性锁水 + 蔬菜细胞壁部分破裂保脆',
   out='质地：脆嫩/嫩滑，不出水\n色泽：油亮、食材本色或美拉德褐\n风味：鲜 + 锅气',
   safe='油温不超烟点；绿叶菜翻炒 <2 分钟、肉类 <3 分钟；复合酱出锅前下（>120℃ 久热挥发损失）'),
 '蒸菜': dict(way='蒸（100℃ 蒸汽，冷凝对流换热，分钟~小时级）',
   react='蛋白质变性、淀粉糊化；无美拉德（无干热表面）→ 色泽靠腌制/酱色',
   out='质地：软嫩多汁、形状完整\n色泽：本色为主\n风味：清鲜、原味突出',
   safe='上汽后再入柜；叶菜 5–8 分钟、肉 15–40 分钟、扣肉类 45–90 分钟；避免中途开盖掉温'),
 '炖菜': dict(way='炖（85–95℃ 微沸，水传导，小时级）',
   react='胶原蛋白水解→明胶（85–95℃ 长时间）+ 风味物溶出与融合 + 脂肪乳化',
   out='质地：酥烂脱骨、汤汁稠\n色泽：酱红/褐\n风味：醇厚复合',
   safe='保持微沸不宜大滚（大滚使肉纤维收缩变柴）；盐后放（早放盐延缓胶原水解）'),
 '炸品': dict(way='油炸（170–190℃，油传导，分钟级）',
   react='表面淀粉糊化→脱水→美拉德/焦糖化（160–180℃）形成脆壳；内部靠热传导蒸熟',
   out='质地：外壳酥脆、内里多汁\n色泽：金黄\n风味：油炸香',
   safe='油温低于烟点；食材表面尽量干燥防溅油；起酥油/棕榈油饱和度高，反复加热易产生极性化合物'),
 '烤类': dict(way='烤（空气传导+辐射，150–250℃）',
   react='美拉德（140–165℃）+ 表面脱水褐变 + 脂肪氧化生香',
   out='质地：外焦里嫩\n色泽：金黄至褐\n风味：烤肉香',
   safe='高脂肉类 200℃+ 长时间易生成杂环胺/多环芳烃，建议中温+翻面+避免明火滴油起烟'),
 '煮锅': dict(way='煮/涮（100℃ 水传导，分钟级）',
   react='蛋白质变性、淀粉糊化；水溶性风味物溶入汤底',
   out='质地：嫩滑\n色泽：本色\n风味：汤底主导',
   safe='生熟分开；叶菜涮 10–30 秒，肉片涮至全熟（中心无血色）'),
 '砂锅菜': dict(way='砂锅（陶砂蓄热强，95–100℃ 微沸，20–60 分钟）',
   react='胶原水解 + 长时间风味融合；砂锅蓄热使降温慢、持续微沸',
   out='质地：酥软入味、汤汁浓\n色泽：酱色/红亮\n风味：厚重',
   safe='砂锅忌骤冷骤热（防裂）；上桌后余温仍高，注意烫伤（DK 2026-08-03 实测教训）'),
 '烫菜': dict(way='焯水/烫（100℃ 水，10–120 秒）',
   react='灭酶护色（叶绿素酶失活）+ 细胞壁软化 + 水溶性维生素溶出',
   out='质地：脆嫩\n色泽：翠绿（加油/盐保色）\n风味：清淡',
   safe='水量要足、大火保持沸腾；时间越短维生素 C 保留越高；捞出后过冷水可锁色（油/盐用少量）'),
 '凉拌': dict(way='凉拌（无热传导，冷加工）',
   react='盐渍渗透压效应脱水入味 + 油相裹覆隔绝氧气 + 酸（醋/柠檬）降低 pH 延缓氧化',
   out='质地：脆爽\n色泽：本色+红油亮\n风味：酸辣鲜香',
   safe='生食蔬菜需流动水洗净（农残/寄生虫）；即拌即食，久置易亚硝酸盐升高；凉拌荤料须彻底冷却且全熟'),
 '卤菜': dict(way='卤（85–95℃ 浸卤，30–120 分钟 + 浸泡）',
   react='胶原水解 + 香辛料挥发油溶入油脂/水相 + 渗透入味（卤水盐分高）',
   out='质地：软糯或紧实（随部位）\n色泽：酱红\n风味：香料复合、回甘',
   safe='卤水须每日烧开保存（防肉毒/腐败）；生熟砧板分开；卤味含盐高，注意钠摄入'),
 '主食': dict(way='蒸/煮/拌（100℃ 湿加热，分钟~小时级）',
   react='淀粉糊化（60–70℃）+ 蛋白质变性；发酵类还含酵母产气与面筋网络形成',
   out='质地：软糯/筋道（随品类）\n色泽：本色\n风味：粮谷香',
   safe='米饭冷藏后复热需彻底（>75℃），防蜡样芽孢杆菌；面条煮后过冷水更弹'),
 '早餐': dict(way='蒸/煮/煎/烤（视单品，100–200℃）',
   react='淀粉糊化 + 蛋白质变性；煎制类叠加美拉德',
   out='质地：松软/酥\n色泽：本色或金黄\n风味：清淡到咸鲜',
   safe='鸡蛋类须熟透（沙门氏菌）；豆浆必须彻底煮沸（皂苷假沸）；隔夜餐食复热到中心 75℃ 以上'),
 '汤': dict(way='炖煮（90–100℃，1–3 小时）',
   react='水溶性风味物与氨基酸溶出 + 胶原水解生明胶 + 脂肪乳化形成乳白汤',
   out='质地：汤清或汤浓、肉酥\n色泽：清亮或乳白\n风味：鲜甜',
   safe='老母鸡/骨头类建议焯水去血沫；久煮的汤嘌呤与钠高，痛风/高血压人群限量'),
 '饮品': dict(way='无烹饪（包装成品或冲调）',
   react='—（非烹饪加工品，热量来源为糖/酒精/乳脂）',
   out='—',
   safe='含糖饮料注意游离糖摄入（WHO 建议 <10% 总能量）；酒精饮品注意总量'),
 '配料': dict(way='复合调味料（中央厨房预制）',
   react='—（官方多未公布配比，无法做反应路径推演）',
   out='—',
   safe='商用复合料多为高钠；家庭替代需自行试味'),
}

def parse(path):
    raw = open(path, encoding='utf-8').read()
    title, img, secs = None, None, None
    secs = []
    cur = None
    for ln in raw.split('\n'):
        s = ln.strip()
        if s.startswith('# ') and title is None:
            title = s[2:].strip(); continue
        if s.startswith('## '):
            cur = [s[3:].strip().rstrip('：:'), 'other', []]
            secs.append(cur); continue
        m = re.match(r'!\[.*?\]\((.*?)\)', s)
        if m:
            img = m.group(1); continue
        if not s or cur is None:
            continue
        cur[2].append(s)
    for sec in secs:
        if ING_HEADS.search(sec[0]):
            sec[1] = 'ing'
        elif STEP_HEADS.search(sec[0]):
            sec[1] = 'step'
    prep = list(dict.fromkeys(re.findall(r'\[([^\]]+)\]\(/配料/', raw)))
    return title, img, secs, raw, prep

def bullets(items):
    out = []
    for l in items:
        if l.startswith('|'):
            out.append(('TABLE', l))
            continue
        t = re.sub(r'^[-*+]\s*', '', l).strip()
        t = re.sub(r'^\d+\s*[.、]\s*', '', t).strip()
        t = re.sub(r'^\d+\s+', '', t).strip()
        t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
        if t:
            out.append(('TEXT', t))
    return out

def classify(ings, other, prep, cat_hint=None):
    blob = ' '.join(ings) + ' || ' + ' '.join(other)
    score, reasons = 0, []
    # 老乡鸡自产预制料：显式链接 + 配料目录同名条目
    named = [n for n in PREP_NAMES if n in blob and n not in prep]
    prep = list(prep) + named
    if prep:
        score += 4
        reasons.append('引用老乡鸡自产预制料：' + '、'.join(prep[:4]) + '（家庭无对应商品）')
    ck = [c for c in PREP_HINT if c in blob]
    if ck:
        score += 5
        reasons.append('配料标注「老乡鸡中央厨房」自产（无零售对应品）')
    brands = sorted([b for b in SUPPLIER_HINT if b != '来自' and b in blob], key=len, reverse=True)
    dedup = []
    for b in brands:
        if not any(b in d for d in dedup):
            dedup.append(b)
    brands = [b for b in dedup if b not in PREP_HINT]
    if brands:
        score += 2 + (1 if len(brands) >= 3 else 0)
        reasons.append(('外购包装商品：' if cat_hint == 'drink' else '配料标注供应商/品牌半成品：') + '、'.join(brands[:3]))
    elif '来自' in blob and not ck:
        score += 2
        m = re.search(r'[（(]来自([^（）()]{2,20})[）)]', blob)
        reasons.append('配料标注来源「%s」' % (m.group(1) if m else '外部供应商'))
    if BRAND_TAIL.search(blob) and not brands and not ck:
        score += 2; reasons.append('配料标注生产企业（工业化半成品）')
    hits = [h for h in HALF_PRODUCT if h in blob]
    if hits:
        score += min(2, len(hits)); reasons.append('含复合/预制料：' + '、'.join(hits[:3]))
    # 名称以「料/酱/汁/膏」结尾且非常见家用调味品 → 复合料
    extra = []
    for i in ings:
        core = re.sub(r'[（(].*', '', i).strip()
        if not core or core in COMMON_COND or core in PREP_NAMES:
            continue
        if re.search(r'(料|酱|汁|膏|粉|油)$', core) and len(core) <= 8:
            extra.append(core)
    if extra and not prep:
        score += min(2, len(extra)); reasons.append('疑似复合调味料需自行调配：' + '、'.join(dict.fromkeys(extra))[:40])
    if '未公布' in blob or '未公开' in blob:
        score += 2; reasons.append('官方未公布配比')
    return ('C' if score >= 3 else 'B' if score >= 1 else 'A'), reasons

def ratio_of(steps):
    nums = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*g', ' '.join(steps))]
    big = [n for n in nums if n >= 50]
    if not big or sum(big) < 200:
        return None, 0
    return round(600.0 / sum(big), 2), int(sum(big))

def params_in(steps):
    """原文中实有的温度/时间参数（只提取，不推断）"""
    t = re.findall(r'\d+\s*(?:℃|°C|度)', ' '.join(steps))
    sec = re.findall(r'\d+\s*(?:秒|分钟|小时|min|h)', ' '.join(steps))
    return t, sec

def main():
    # ---- 1. raw 语料逐字入库 ----
    os.makedirs(RAW, exist_ok=True)   # 保留已有内容（README 等），仅覆盖同名文件
    copied = 0
    for cat in CATS:
        d = os.path.join(SRC, cat)
        od = os.path.join(RAW, cat)
        os.makedirs(od, exist_ok=True)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.md') or fn == 'README.md':
                continue
            shutil.copy2(os.path.join(d, fn), os.path.join(od, fn))
            copied += 1
    # 图片不入库：192 张 6.3MB 只覆盖 339 条里的 179 条，对"在家能不能做"零贡献。
    # 需要看成品图去上游仓库 images/ 目录，或 https://cooklikehoc.soilzhu.su 。

    # ---- 2. build 编译页 ----
    os.makedirs(WIKI, exist_ok=True)
    for f in os.listdir(WIKI):
        if f.endswith('.md'):
            os.remove(os.path.join(WIKI, f))
    dk_names = set()
    for sub in ['ingredients', 'techniques', 'chemistry', 'concepts', 'nutrition']:
        p = os.path.join(DK, 'wiki', sub)
        if os.path.isdir(p):
            for f in os.listdir(p):
                if f.endswith('.md') and not f.startswith('index'):
                    dk_names.add(f[:-3])
    dk_names |= set(x for x in ['美拉德反应','蛋白质变性','淀粉糊化','焦糖化反应','胶原蛋白水解','脂肪氧化','维生素C','维生素C氧化','抗氧化物质','焯水','油炸','火候','炒','炖','蒸','煮','煎','腌','凉拌','卤','红烧','烧','白灼','勾芡','刀工','调味','调味料下锅时机','防溅油'])

    rows = []
    used = {}
    for cat in CATS:
        d = os.path.join(RAW, cat)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.md'):
                continue
            title, img, secs, rawtext, prep = parse(os.path.join(d, fn))
            title = title or fn[:-3]
            ings, steps, others, tables = [], [], [], []
            for head, role, items in secs:
                for kind, t in bullets(items):
                    if kind == 'TABLE':
                        tables.append(t)
                    elif role == 'ing':
                        ings.append(t)
                    elif role == 'step':
                        steps.append(t)
                    else:
                        others.append(t)
            grade, reasons = classify(ings, others, prep, 'drink' if cat == '饮品' else None)
            ratio, total = ratio_of(steps)
            temps, times = params_in(steps)
            key = title
            if key in used:
                key = '%s（%s）' % (title, cat)
            used[title] = 1
            fname = key.replace('/', '／') + '.md'
            rows.append(dict(cat=cat, title=title, fname=fname, src=fn, grade=grade,
                             reasons=reasons, ing=ings, step=steps, other=others, prep=prep,
                             tables=tables, ratio=ratio, total=total, img=img,
                             temps=temps, times=times))

    # 交叉链接：配料名 → DK 已有页面
    for r in rows:
        links = []
        blob = ' '.join(r['ing'])
        for n in sorted(dk_names, key=len, reverse=True):
            if len(n) >= 2 and n in blob:
                links.append(n)
                blob = blob.replace(n, '　')
        r['links'] = links[:12]

    for r in rows:
        write_page(r)

    write_index(rows)
    print('raw 逐字入库:', copied, '| wiki 编译页:', len(rows))
    print('分级:', dict(Counter(r['grade'] for r in rows)))
    json.dump([{k: v for k, v in r.items() if k != 'tables'} for r in rows],
              open('/tmp/dk_import/final.json', 'w'), ensure_ascii=False, indent=1)

def fmttable(t):
    return '| ' + t.strip('|').replace('|', ' | ') + ' |'

def write_page(r):
    """紧凑页：只写这一道菜独有的内容。
    分类级样板（因子/预期成品/安全边界/缩放通则/置信度口径）统一在 index.md 的「分类速查」里，不逐页重复。"""
    L = []
    L.append('# 老乡鸡 · %s' % r['title'])
    L.append('')
    L.append('> 原文 `raw/cooklikehoc/%s/%s` · 分类 **%s** · 复现等级 **%s** · 导入 %s'
             % (r['cat'], r['src'], r['cat'], r['grade'], DATE))
    L.append('> 本类烹饪原理 / 预期成品 / 安全边界 / 缩放通则 → 见 [index](index.md#%s)' % r['cat'])
    L.append('')
    head = []
    if r['ratio']:
        if r['ratio'] < 0.9:
            head.append('- 门店批量：主料合计约 %dg → 家庭 2 人份 **×%s**' % (r['total'], r['ratio']))
        else:
            head.append('- 主料合计约 %dg，已接近家庭 2 人份，无需缩放' % r['total'])
    if r['temps']:
        head.append('- 原文温度：%s' % '、'.join(dict.fromkeys(r['temps'])))
    if r['times']:
        head.append('- 原文时间：%s' % '、'.join(dict.fromkeys(r['times'])))
    if r['grade'] == 'A':
        head.append('- 复现等级 A：全部常见食材，家常可直接做')
    if head:
        L += head
        L.append('')
    if r['prep']:
        L.append('**需自配的预制料**（老乡鸡中央厨房产，官方未公布配比，成分见 `raw/cooklikehoc/配料/`）：%s'
                 % '、'.join(r['prep']))
        L.append('')
    if r['reasons'] and r['grade'] != 'A':
        L.append('复现依据：' + ' · '.join(r['reasons']))
        L.append('')
    L.append('## 配料（原文）')
    L.append('')
    if r['ing']:
        for x in r['ing']:
            L.append('- %s' % x)
    else:
        L.append('- （原文无配料表）')
    L.append('')
    if r['other']:
        L.append('## 其它（原文）')
        L.append('')
        for x in r['other']:
            L.append('- %s' % x)
        L.append('')
    L.append('## 步骤（原文）')
    L.append('')
    if r['step']:
        for i, x in enumerate(r['step'], 1):
            L.append('%d. %s' % (i, x))
    else:
        L.append('（原文无步骤：复合调味料 / 包装商品，仅登记配料或名称）')
    L.append('')
    if r['tables']:
        L.append('## 营养成分（原文，每 100g）')
        L.append('')
        L.append(r['tables'][0])
        L.append('')
    if r['links']:
        L.append('相关：' + ' · '.join('[[%s]]' % x for x in r['links']))
        L.append('')
    open(os.path.join(WIKI, r['fname']), 'w', encoding='utf-8').write('\n'.join(L))


def write_index(rows):
    """总览页：等级判据 + 缩放通则 + 置信度口径 + 15 类因子速查 + 全量清单。"""
    bycat = defaultdict(list)
    for r in rows:
        bycat[r['cat']].append(r)
    g = Counter(r['grade'] for r in rows)
    L = []
    L.append('# 老乡鸡菜谱总览（CookLikeHOC 导入）')
    L.append('')
    L.append('> 来源：[cooklikehoc.soilzhu.su](https://cooklikehoc.soilzhu.su) ← GitHub [Gar-b-age/CookLikeHOC](https://github.com/Gar-b-age/CookLikeHOC)，内容整理自《老乡鸡菜品溯源报告》')
    L.append('> 条目 %d · 原文语料 `raw/cooklikehoc/` · 重新生成：`python3 scripts/import-cooklikehoc.py`' % len(rows))
    L.append('')
    L.append('## 复现等级')
    L.append('')
    L.append('| 等级 | 含义 | 数量 |')
    L.append('|------|------|------|')
    L.append('| A | 全部常见食材，家常可直接做 | %d |' % g['A'])
    L.append('| B | 含品牌半成品或复合料，需替代 | %d |' % g['B'])
    L.append('| C | 依赖老乡鸡中央厨房自产料／官方未公布配比，只能近似复刻 | %d |' % g['C'])
    L.append('')
    L.append('判据（按权重）：引用 `配料/` 自产预制料 或 标注「中央厨房」→ C；标注供应商品牌 → B 起；'
             '名称以料/酱/汁/膏结尾且非常见家用调味品 → B；官方注明未公布配比 → C。')
    L.append('')
    L.append('## 缩放通则（所有条目共用，单页不再重复）')
    L.append('')
    L.append('这批配方全是**中央厨房/门店出品口径**，不是家庭食谱。单页只给系数，用法如下：')
    L.append('')
    L.append('1. 系数 = 600g ÷ 步骤中主料量合计（≥50g 的项），目标家庭 2 人份')
    L.append('2. 盐、鸡精、复合酱**先按系数的 70–80% 下**，尝味再补——商业配方咸鲜度高于家庭口味')
    L.append('3. 油量**直接砍到 1/3~1/2**——门店靠大量油控温/过油，家庭锅具不需要')
    L.append('4. 原文温度与时间可沿用；家庭灶火力弱于商用灶，以「食材状态」为准（肉变色、菜断生）')
    L.append('5. 系数 >1 说明原文已是家庭量级，只处理第 2、3 条')
    L.append('')
    L.append('## 置信度口径')
    L.append('')
    L.append('- **配料 / 步骤 / 营养表**：中高 — 老乡鸡官方《菜品溯源报告》一手公开资料，但门店口径、工艺细节不全')
    L.append('- **因子分析 / 预期成品 / 安全边界**（下表）：中 — DK 按烹饪原理推演的**分类通例**，非原文')
    L.append('- **缩放系数**：中低 — 按主料总量估算，**未经实测**')
    L.append('')
    L.append('## 分类速查（因子 · 成品 · 安全）')
    L.append('')
    L.append('| 分类 | 烹饪方式因子 | 激活的反应路径 | 预期成品 | 安全边界 |')
    L.append('|------|------------|--------------|---------|---------|')
    for cat in CATS:
        if cat not in bycat:
            continue
        f = CAT_FACTOR[cat]
        L.append('| **%s** | %s | %s | %s | %s |' % (
            cat, f['way'], f['react'], f['out'].replace('\n', '；'), f['safe']))
    L.append('')
    L.append('## 全量清单')
    L.append('')
    for cat in CATS:
        rs = bycat.get(cat, [])
        if not rs:
            continue
        L.append('### %s（%d）' % (cat, len(rs)))
        L.append('')
        for r in sorted(rs, key=lambda x: x['title']):
            mark = {'A': '🟢', 'B': '🟡', 'C': '🔴'}[r['grade']]
            extra = ''
            if r['ratio'] and r['ratio'] < 0.9:
                extra = ' ×%s' % r['ratio']
            elif r['ratio']:
                extra = ' 免缩放'
            if r['prep']:
                extra += ' ｜预制料：' + '、'.join(r['prep'][:2])
            L.append('- %s [[%s]]%s' % (mark, r['fname'][:-3], extra))
        L.append('')
    open(os.path.join(WIKI, 'index.md'), 'w', encoding='utf-8').write('\n'.join(L))

main()
