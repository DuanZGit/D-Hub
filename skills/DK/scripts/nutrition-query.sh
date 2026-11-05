#!/usr/bin/env bash
# 营养与化学反应查询脚本
# 用法: ./nutrition-query.sh <类型> [关键词]

DB_NUTRITION="$(dirname "$0")/../db/nutrition-v2.db"
TYPE=${1:-"help"}
KEYWORD=${2:-""}

# 初始化数据库
init_db() {
  if [ ! -f "$DB_NUTRITION" ]; then
    echo "初始化营养数据库..."
    sqlite3 "$DB_NUTRITION" < "$(dirname "$0")/../db/nutrition-v2-schema.sql"
    sqlite3 "$DB_NUTRITION" < "$(dirname "$0")/../db/nutrition-v2-data.sql"
    echo "初始化完成！"
  fi
}

# 查询食材营养
query_nutrition() {
  echo "============================================================"
  echo "【食材营养成分查询】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT name as 食材, category as 分类, calories as 热量, 
             protein as 蛋白质, fat as 脂肪, carbs as 碳水,
             fiber as 膳食纤维,
             COALESCE(source_platform,'') as 来源平台,
             COALESCE(source_url,'') as 来源网址
      FROM ingredient_nutrition ORDER BY category, name;
    "
  else
    echo ""
    echo "【$KEYWORD 营养成分】"
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT name, calories, protein, fat, carbs, fiber, water,
             vitamin_c, vitamin_a, calcium, iron, zinc, selenium,
             COALESCE(source_platform,'') as 来源平台,
             COALESCE(source_title,'') as 来源标题,
             COALESCE(source_url,'') as 来源网址,
             COALESCE(source_method,'') as 采集方式
      FROM ingredient_nutrition WHERE name LIKE '%$KEYWORD%';
    "
    
    echo ""
    echo "【氨基酸含量】"
    sqlite3 "$DB_NUTRITION" "
      SELECT '亮氨酸:' || leucine || ', 异亮氨酸:' || isoleucine || 
             ', 缬氨酸:' || valine || ', 赖氨酸:' || lysine
      FROM ingredient_nutrition WHERE name LIKE '%$KEYWORD%';
    "
    
    echo ""
    echo "【脂肪酸】"
    sqlite3 "$DB_NUTRITION" "
      SELECT 'Omega-3:' || omega_3 || 'g, Omega-6:' || omega_6 || 
             'g, Omega-9:' || omega_9 || 'g, 饱和脂肪:' || saturated_fat || 'g'
      FROM ingredient_nutrition WHERE name LIKE '%$KEYWORD%';
    "
    
    echo ""
    echo "【升糖指数】"
    sqlite3 "$DB_NUTRITION" "
      SELECT 'GI值:' || gi_index || ' (低GI<55, 中GI 55-70, 高GI>70)'
      FROM ingredient_nutrition WHERE name LIKE '%$KEYWORD%';
    "
  fi
}

# 查询调料成分
query_condiment() {
  echo "============================================================"
  echo "【调料成分查询】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT name as 调料, main_compounds as 主要成分, 
             functions as 功能, daily_limit as 每日限量
      FROM condiment_info;
    "
  else
    sqlite3 "$DB_NUTRITION" "
      SELECT '调料:' || name,
             '主要成分:' || main_compounds,
             '风味化合物:' || flavor_compounds,
             '活性成分:' || active_compounds,
             '功能:' || functions,
             '机理:' || mechanism,
             '益处:' || benefits,
             '风险:' || risks,
             '每日限量:' || daily_limit
      FROM condiment_info WHERE name LIKE '%$KEYWORD%';
    "
  fi
}

# 查询化学反应
query_reaction() {
  echo "============================================================"
  echo "【食品化学反应查询】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT name as 反应, name_en as 英文名, category as 分类,
             temperature_min || '-' || temperature_max || '°C' as 温度范围,
             COALESCE(source_platform,'') as 来源平台,
             COALESCE(source_url,'') as 来源网址
      FROM chemical_reactions;
    "
  else
    sqlite3 "$DB_NUTRITION" "
      SELECT '反应:' || name || ' (' || name_en || ')',
             '分类:' || category,
             '温度:' || temperature_min || '-' || temperature_max || '°C',
             '机理:' || mechanism,
             '反应物:' || reactants,
             '产物:' || final_products,
             '颜色变化:' || color_change,
             '风味变化:' || flavor_change,
             '有益产物:' || beneficial_products,
             '有害产物:' || harmful_products,
             '健康影响:' || health_impact,
             '促进方法:' || promote_methods,
             '抑制方法:' || inhibit_methods,
             '应用:' || applications,
             '实例:' || examples
      FROM chemical_reactions WHERE name LIKE '%$KEYWORD%' OR name_en LIKE '%$KEYWORD%';
    "
  fi
}

# 查询营养相互作用
query_interaction() {
  echo "============================================================"
  echo "【营养相互作用查询】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT nutrient1 as 营养素1, nutrient2 as 营养素2, 
             interaction_type as 类型, health_impact as 健康影响,
             COALESCE(ref_source,'') as 参考来源
      FROM nutrient_interactions;
    "
  else
    sqlite3 "$DB_NUTRITION" "
      SELECT nutrient1 || ' + ' || nutrient2 || ' [' || interaction_type || ']',
             '机理:' || mechanism,
             '吸收影响:' || absorption_effect,
             '健康影响:' || health_impact,
             '食物实例:' || food_examples,
             '建议:' || recommendation,
             '证据级别:' || evidence_level
      FROM nutrient_interactions 
      WHERE nutrient1 LIKE '%$KEYWORD%' OR nutrient2 LIKE '%$KEYWORD%';
    "
  fi
}

# 查询烹饪对营养的影响
query_cooking_impact() {
  echo "============================================================"
  echo "【烹饪对营养的影响】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT cooking_method as 烹饪方式, 
             vitamin_c_retention || '%' as 维C保留,
             vitamin_b_retention || '%' as 维B保留,
             protein_retention || '%' as 蛋白质保留,
             harmful_effects as 有害效应
      FROM cooking_nutrition_impact;
    "
  else
    sqlite3 "$DB_NUTRITION" "
      SELECT '烹饪方式:' || cooking_method,
             '温度:' || typical_temp,
             '时间:' || typical_duration,
             '维C保留率:' || vitamin_c_retention || '%',
             '维B保留率:' || vitamin_b_retention || '%',
             '维A保留率:' || vitamin_a_retention || '%',
             '矿物质保留率:' || mineral_retention || '%',
             '蛋白质保留率:' || protein_retention || '%',
             '营养流失:' || nutrient_loss,
             '营养增加:' || nutrient_gain,
             '主要反应:' || main_reactions,
             '有益效应:' || beneficial_effects,
             '有害效应:' || harmful_effects,
             '最适合:' || best_for,
             '不适合:' || not_good_for,
             '建议:' || tips
      FROM cooking_nutrition_impact WHERE cooking_method LIKE '%$KEYWORD%';
    "
  fi
}

# 查询食材搭配
query_synergy() {
  echo "============================================================"
  echo "【食材搭配效应查询】"
  echo "============================================================"
  
  if [ -z "$KEYWORD" ]; then
    sqlite3 -header -column "$DB_NUTRITION" "
      SELECT food1 as 食材1, food2 as 食材2, 
             effect_type as 效应类型, health_benefit as 健康益处,
             COALESCE(source_platform,'') as 来源平台,
             COALESCE(source_url,'') as 来源网址
      FROM food_synergy;
    "
  else
    sqlite3 "$DB_NUTRITION" "
      SELECT food1 || ' + ' || food2 || ' [' || effect_type || ']',
             '营养协同:' || nutrient_synergy,
             '吸收增强:' || absorption_enhancement,
             '化学反应:' || chemical_interaction,
             '健康益处:' || health_benefit,
             '健康风险:' || health_risk,
             '机理:' || mechanism,
             '建议:' || recommendation
      FROM food_synergy 
      WHERE food1 LIKE '%$KEYWORD%' OR food2 LIKE '%$KEYWORD%';
    "
  fi
}

# 综合分析
analyze_dish() {
  echo "============================================================"
  echo "【菜品营养分析】"
  echo "============================================================"
  echo "请输入菜品名称或食材组合：$KEYWORD"
  echo ""
  echo "功能：分析食材营养、化学反应、搭配效应"
  echo "（此功能需要根据具体菜品动态分析）"
}

# 显示帮助
show_help() {
  echo "============================================================"
  echo "营养与化学反应查询"
  echo "============================================================"
  echo ""
  echo "用法: ./nutrition-query.sh <类型> [关键词]"
  echo ""
  echo "查询类型："
  echo "  nutrition    - 食材营养成分"
  echo "  condiment    - 调料成分"
  echo "  reaction     - 化学反应"
  echo "  interaction  - 营养相互作用"
  echo "  impact       - 烹饪对营养的影响"
  echo "  synergy      - 食材搭配效应"
  echo ""
  echo "示例："
  echo "  ./nutrition-query.sh nutrition 番茄"
  echo "  ./nutrition-query.sh condiment 盐"
  echo "  ./nutrition-query.sh reaction 美拉德"
  echo "  ./nutrition-query.sh interaction 铁"
  echo "  ./nutrition-query.sh impact 蒸"
  echo "  ./nutrition-query.sh synergy 番茄"
  echo ""
  echo "数据来源："
  echo "  - 中国食物成分表"
  echo "  - USDA食品数据库"
  echo "  - 食品化学教材"
  echo "  - 营养学研究文献"
  echo "============================================================"
}

# 初始化数据库
init_db

# 根据参数执行查询
case $TYPE in
  "nutrition"|"营养")
    query_nutrition
    ;;
  "condiment"|"调料")
    query_condiment
    ;;
  "reaction"|"反应"|"化学")
    query_reaction
    ;;
  "interaction"|"相互作用")
    query_interaction
    ;;
  "impact"|"影响"|"烹饪")
    query_cooking_impact
    ;;
  "synergy"|"搭配")
    query_synergy
    ;;
  "analyze"|"分析")
    analyze_dish
    ;;
  *)
    show_help
    ;;
esac
