-- 营养与化学反应知识库

-- ============================================================
-- 1. 食材营养成分表
-- ============================================================
CREATE TABLE IF NOT EXISTS ingredient_nutrition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 食材名称
    category TEXT,                   -- 分类：肉类/蔬菜/水果/谷物/豆制品/调味料
    
    -- 宏量营养素（每100g）
    calories REAL,                   -- 热量(kcal)
    protein REAL,                    -- 蛋白质(g)
    fat REAL,                        -- 脂肪(g)
    carbs REAL,                      -- 碳水化合物(g)
    fiber REAL,                      -- 膳食纤维(g)
    
    -- 维生素
    vitamin_a REAL,                  -- 维生素A(μg)
    vitamin_b1 REAL,                 -- 维生素B1/硫胺素(mg)
    vitamin_b2 REAL,                 -- 维生素B2/核黄素(mg)
    vitamin_b6 REAL,                 -- 维生素B6(mg)
    vitamin_b12 REAL,                -- 维生素B12(μg)
    vitamin_c REAL,                  -- 维生素C(mg)
    vitamin_d REAL,                  -- 维生素D(μg)
    vitamin_e REAL,                  -- 维生素E(mg)
    vitamin_k REAL,                  -- 维生素K(μg)
    folate REAL,                     -- 叶酸(μg)
    
    -- 矿物质
    calcium REAL,                    -- 钙(mg)
    iron REAL,                       -- 铁(mg)
    zinc REAL,                       -- 锌(mg)
    magnesium REAL,                  -- 镁(mg)
    potassium REAL,                  -- 钾(mg)
    phosphorus REAL,                 -- 磷(mg)
    selenium REAL,                   -- 硒(μg)
    sodium REAL,                     -- 钠(mg)
    
    -- 特性
    properties TEXT,                 -- 食材特性（寒性/温性/平等）
    flavor TEXT,                     -- 味道（甘/苦/酸/辛/咸）
   功效 TEXT,                        -- 中医功效
    suitable_for TEXT,               -- 适宜人群
    not_suitable_for TEXT,           -- 不适宜人群
    
    -- 存储和处理
    storage_advice TEXT,             -- 储存建议
    best_season TEXT,                -- 最佳季节
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 2. 调料营养与特性表
-- ============================================================
CREATE TABLE IF NOT EXISTS condiment_nutrition (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 调料名称
    
    -- 主要成分
    main_components TEXT,            -- 主要成分
    flavor_compounds TEXT,           -- 风味化合物
    
    -- 营养（每100g或适量使用时）
    calories REAL,
    sodium REAL,                     -- 钠(mg)
    potassium REAL,                  -- 钾(mg)
    
    -- 特性
    flavor_profile TEXT,             -- 风味特点
    function_text TEXT,              -- 功能作用
    
    -- 健康影响
    health_benefits TEXT,            -- 健康益处
    health_risks TEXT,               -- 健康风险
    daily_limit TEXT,                -- 每日限量
    
    -- 使用建议
    best_used_with TEXT,             -- 最佳搭配
    avoid_with TEXT,                 -- 避免搭配
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 3. 烹饪化学反应表
-- ============================================================
CREATE TABLE IF NOT EXISTS cooking_reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reaction_name TEXT NOT NULL,     -- 反应名称
    reaction_name_en TEXT,           -- 英文名
    
    -- 反应条件
    temperature_min REAL,            -- 最低温度(°C)
    temperature_max REAL,            -- 最高温度(°C)
    ph_range TEXT,                   -- pH范围
    time_required TEXT,              -- 所需时间
    
    -- 反应物
    reactants TEXT,                  -- 参与反应的物质
    
    -- 生成物
    products_beneficial TEXT,        -- 有益生成物
    products_harmful TEXT,           -- 有害生成物
    
    -- 反应描述
    description TEXT,                -- 反应描述
    mechanism TEXT,                  -- 反应机理
    
    -- 影响因素
    factors_promoting TEXT,          -- 促进因素
    factors_inhibiting TEXT,         -- 抑制因素
    
    -- 应用
    cooking_applications TEXT,       -- 烹饪应用
    examples TEXT,                   -- 实例
    
    -- 健康影响
    health_impact TEXT,              -- 健康影响
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. 食材搭配表
-- ============================================================
CREATE TABLE IF NOT EXISTS food_pairing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food1 TEXT NOT NULL,             -- 食材1
    food2 TEXT NOT NULL,             -- 食材2
    
    -- 搭配类型
    pairing_type TEXT,               -- 有益搭配/有害搭配/中性搭配
    
    -- 营养协同
    nutrient_synergy TEXT,           -- 营养协同效应
    
    -- 化学反应
    chemical_reaction TEXT,          -- 化学反应
    reaction_products TEXT,          -- 反应产物
    
    -- 健康影响
    health_benefit TEXT,             -- 健康益处
    health_risk TEXT,                -- 健康风险
    
    -- 科学依据
    scientific_evidence TEXT,        -- 科学依据
    evidence_level TEXT,             -- 证据级别：强/中/弱
    
    -- 建议
    recommendation TEXT,             -- 建议
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 5. 做法对营养的影响表
-- ============================================================
CREATE TABLE IF NOT EXISTS cooking_method_impact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cooking_method TEXT NOT NULL,    -- 烹饪方式
    
    -- 营养保留率
    vitamin_c_retention REAL,        -- 维生素C保留率(%)
    vitamin_b_retention REAL,        -- 维生素B保留率(%)
    mineral_retention REAL,          -- 矿物质保留率(%)
    protein_digestibility REAL,      -- 蛋白质消化率(%)
    
    -- 营养变化
    nutrient_loss TEXT,              -- 营养流失
    nutrient_gain TEXT,              -- 营养增加
    
    -- 化学反应
    beneficial_reactions TEXT,       -- 有益反应
    harmful_reactions TEXT,          -- 有害反应
    
    -- 健康影响
    health_impact TEXT,              -- 总体健康影响
    
    -- 最佳实践
    best_for TEXT,                   -- 最适合的食材
    tips TEXT,                       -- 建议
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 6. 食材成分特性表
-- ============================================================
CREATE TABLE IF NOT EXISTS ingredient_properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 食材名称
    
    -- 主要成分
    active_compounds TEXT,           -- 活性成分
    antioxidants TEXT,               -- 抗氧化物质
    phytochemicals TEXT,             -- 植物化学物质
    
    -- 特性
    solubility TEXT,                 -- 溶解性（水溶性/脂溶性）
    heat_sensitivity TEXT,           -- 热敏感性
    oxidation_sensitivity TEXT,      -- 氧化敏感性
    
    -- 烹饪特性
    cooking_behavior TEXT,           -- 烹饪行为
    flavor_release TEXT,             -- 风味释放条件
    
    -- 健康功效
    health_effects TEXT,             -- 健康功效
    therapeutic_uses TEXT,           -- 药用价值
    
    -- 注意事项
    contraindications TEXT,          -- 禁忌
    interactions TEXT,               -- 相互作用
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_ingredient_nutrition_name ON ingredient_nutrition(name);
CREATE INDEX IF NOT EXISTS idx_condiment_nutrition_name ON condiment_nutrition(name);
CREATE INDEX IF NOT EXISTS idx_cooking_reactions_name ON cooking_reactions(reaction_name);
CREATE INDEX IF NOT EXISTS idx_food_pairing_food1 ON food_pairing(food1);
CREATE INDEX IF NOT EXISTS idx_food_pairing_food2 ON food_pairing(food2);
CREATE INDEX IF NOT EXISTS idx_cooking_method_impact_method ON cooking_method_impact(cooking_method);
CREATE INDEX IF NOT EXISTS idx_ingredient_properties_name ON ingredient_properties(name);
