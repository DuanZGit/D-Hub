CREATE TABLE ingredient_nutrition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 食材名称
    category TEXT,                   -- 分类：肉类/蔬菜/水果/谷物/豆制品/水产/蛋奶
    
    -- 宏量营养素
    calories REAL,                   -- 热量(kcal)
    protein REAL,                    -- 蛋白质(g)
    fat REAL,                        -- 脂肪(g)
    saturated_fat REAL,              -- 饱和脂肪(g)
    unsaturated_fat REAL,            -- 不饱和脂肪(g)
    carbs REAL,                      -- 碳水化合物(g)
    sugar REAL,                      -- 糖(g)
    fiber REAL,                      -- 膳食纤维(g)
    water REAL,                      -- 水分(g)
    
    -- 维生素
    vitamin_a REAL,                  -- 维生素A(μg RAE)
    vitamin_b1 REAL,                 -- 硫胺素(mg)
    vitamin_b2 REAL,                 -- 核黄素(mg)
    vitamin_b3 REAL,                 -- 烟酸(mg)
    vitamin_b5 REAL,                 -- 泛酸(mg)
    vitamin_b6 REAL,                 -- 吡哆醇(mg)
    vitamin_b12 REAL,                -- 钴胺素(μg)
    vitamin_c REAL,                  -- 抗坏血酸(mg)
    vitamin_d REAL,                  -- 钙化醇(μg)
    vitamin_e REAL,                  -- 生育酚(mg)
    vitamin_k REAL,                  -- 叶绿醌(μg)
    folate REAL,                     -- 叶酸(μg)
    choline REAL,                    -- 胆碱(mg)
    
    -- 矿物质
    calcium REAL,                    -- 钙(mg)
    iron REAL,                       -- 铁(mg)
    zinc REAL,                       -- 锌(mg)
    magnesium REAL,                  -- 镁(mg)
    potassium REAL,                  -- 钾(mg)
    phosphorus REAL,                 -- 磷(mg)
    selenium REAL,                   -- 硒(μg)
    sodium REAL,                     -- 钠(mg)
    copper REAL,                     -- 铜(mg)
    manganese REAL,                  -- 锰(mg)
    
    -- 氨基酸（必需氨基酸，mg/g蛋白质）
    leucine REAL,                    -- 亮氨酸
    isoleucine REAL,                 -- 异亮氨酸
    valine REAL,                     -- 缬氨酸
    lysine REAL,                     -- 赖氨酸
    methionine REAL,                 -- 蛋氨酸
    phenylalanine REAL,              -- 苯丙氨酸
    threonine REAL,                  -- 苏氨酸
    tryptophan REAL,                 -- 色氨酸
    histidine REAL,                  -- 组氨酸
    
    -- 脂肪酸
    omega_3 REAL,                    -- Omega-3(g)
    omega_6 REAL,                    -- Omega-6(g)
    omega_9 REAL,                    -- Omega-9(g)
    
    -- 特性
    gi_index REAL,                   -- 升糖指数(0-100)
    gl_index REAL,                   -- 升糖负荷
    pral REAL,                       -- 潜在肾酸负荷
    
    -- 储存
    storage TEXT,                    -- 储存建议
    shelf_life TEXT,                 -- 保质期
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE condiment_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 调料名称
    
    -- 主要成分
    main_compounds TEXT,             -- 主要化合物
    flavor_compounds TEXT,           -- 风味化合物
    active_compounds TEXT,           -- 活性成分
    
    -- 营养（每100g或每份）
    serving_size TEXT,               -- 份量
    calories REAL,
    sodium REAL,                     -- 钠(mg)
    potassium REAL,                  -- 钾(mg)
    
    -- 化学特性
    ph_value REAL,                   -- pH值
    osmotic_effect TEXT,             -- 渗透压效应
    antioxidant_capacity TEXT,       -- 抗氧化能力
    
    -- 烹饪功能
    functions TEXT,                  -- 烹饪功能（增香/上色/嫩化等）
    mechanism TEXT,                  -- 作用机理
    
    -- 健康影响
    benefits TEXT,                   -- 益处
    risks TEXT,                      -- 风险
    daily_limit TEXT,                -- 每日限量
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE chemical_reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 反应名称
    name_en TEXT,                    -- 英文名
    category TEXT,                   -- 分类：美拉德/焦糖化/氧化/水解/酯化等
    
    -- 反应条件
    temperature_min REAL,            -- 最低温度(°C)
    temperature_max REAL,            -- 最高温度(°C)
    optimal_ph TEXT,                 -- 最适pH
    water_activity TEXT,             -- 水分活度
    time_factor TEXT,                -- 时间因素
    catalysts TEXT,                  -- 催化剂/促进剂
    
    -- 反应机理
    mechanism TEXT,                  -- 反应机理
    reactants TEXT,                  -- 反应物
    intermediates TEXT,              -- 中间产物
    final_products TEXT,             -- 最终产物
    
    -- 感官影响
    color_change TEXT,               -- 颜色变化
    flavor_change TEXT,              -- 风味变化
    texture_change TEXT,             -- 质地变化
    aroma_change TEXT,               -- 香气变化
    
    -- 健康影响
    beneficial_products TEXT,        -- 有益产物
    harmful_products TEXT,           -- 有害产物
    health_impact TEXT,              -- 健康影响
    
    -- 控制方法
    promote_methods TEXT,            -- 促进方法
    inhibit_methods TEXT,            -- 抑制方法
    
    -- 应用实例
    applications TEXT,               -- 应用
    examples TEXT,                   -- 实例
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE nutrient_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nutrient1 TEXT NOT NULL,         -- 营养素1
    nutrient2 TEXT NOT NULL,         -- 营养素2
    
    -- 相互作用类型
    interaction_type TEXT,           -- 协同/拮抗/无影响
    
    -- 作用机理
    mechanism TEXT,                  -- 机理描述
    absorption_effect TEXT,          -- 吸收影响
    
    -- 健康影响
    health_impact TEXT,              -- 健康影响
    
    -- 实际应用
    food_examples TEXT,              -- 食物实例
    recommendation TEXT,             -- 建议
    
    -- 证据
    evidence_level TEXT,             -- 证据级别：强/中/弱
    ref_source TEXT                  -- 参考来源
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE cooking_nutrition_impact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cooking_method TEXT NOT NULL,    -- 烹饪方式
    
    -- 温度和时间
    typical_temp TEXT,               -- 典型温度
    typical_duration TEXT,           -- 典型时间
    
    -- 营养保留率（%）
    vitamin_c_retention REAL,
    vitamin_b_retention REAL,
    vitamin_a_retention REAL,
    mineral_retention REAL,
    protein_retention REAL,
    fat_retention REAL,
    fiber_retention REAL,
    
    -- 营养变化
    nutrient_loss TEXT,              -- 流失的营养
    nutrient_gain TEXT,              -- 增加的营养
    bioavailability_change TEXT,     -- 生物利用度变化
    
    -- 化学反应
    main_reactions TEXT,             -- 主要反应
    beneficial_effects TEXT,         -- 有益效应
    harmful_effects TEXT,            -- 有害效应
    
    -- 食材适用性
    best_for TEXT,                   -- 最适合
    not_good_for TEXT,               -- 不适合
    
    -- 优化建议
    tips TEXT,                       -- 建议
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE food_synergy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food1 TEXT NOT NULL,
    food2 TEXT NOT NULL,
    
    -- 效应类型
    effect_type TEXT,                -- 正协同/负协同/无影响
    
    -- 营养协同
    nutrient_synergy TEXT,           -- 营养协同
    absorption_enhancement TEXT,     -- 吸收增强
    
    -- 化学反应
    chemical_interaction TEXT,       -- 化学相互作用
    reaction_products TEXT,          -- 反应产物
    
    -- 健康影响
    health_benefit TEXT,
    health_risk TEXT,
    
    -- 科学依据
    mechanism TEXT,
    evidence TEXT,
    
    -- 建议
    recommendation TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE INDEX idx_nutrition_name ON ingredient_nutrition(name);
CREATE INDEX idx_nutrition_category ON ingredient_nutrition(category);
CREATE INDEX idx_condiment_name ON condiment_info(name);
CREATE INDEX idx_reaction_name ON chemical_reactions(name);
CREATE INDEX idx_reaction_category ON chemical_reactions(category);
CREATE INDEX idx_interaction_nutrient1 ON nutrient_interactions(nutrient1);
CREATE INDEX idx_interaction_nutrient2 ON nutrient_interactions(nutrient2);
CREATE INDEX idx_impact_method ON cooking_nutrition_impact(cooking_method);
CREATE INDEX idx_synergy_food1 ON food_synergy(food1);
CREATE INDEX idx_synergy_food2 ON food_synergy(food2);
CREATE TABLE source_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  title TEXT,
  url TEXT NOT NULL,
  method TEXT,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
