
-- ingredient_nutrition
-- 已有 health_risk 字段(类似 health_warnings),加 evidence_url
ALTER TABLE ingredient_nutrition ADD COLUMN evidence_url TEXT;

-- condiment_info
ALTER TABLE condiment_info ADD COLUMN evidence_url TEXT;
ALTER TABLE condiment_info ADD COLUMN health_warnings TEXT;

-- chemical_reactions
ALTER TABLE chemical_reactions ADD COLUMN evidence_url TEXT;
ALTER TABLE chemical_reactions ADD COLUMN health_warnings TEXT;

-- nutrient_interactions
-- 已有 health_impact,加 evidence_url
ALTER TABLE nutrient_interactions ADD COLUMN evidence_url TEXT;

-- cooking_nutrition_impact
ALTER TABLE cooking_nutrition_impact ADD COLUMN evidence_url TEXT;

-- food_synergy
ALTER TABLE food_synergy ADD COLUMN evidence_url TEXT;
ALTER TABLE food_synergy ADD COLUMN health_warnings TEXT;

-- 索引(只为本 DB 内的表)
CREATE INDEX IF NOT EXISTS idx_evidence_url_ingredient_nutrition ON ingredient_nutrition(evidence_url);
CREATE INDEX IF NOT EXISTS idx_evidence_url_chemical_reactions ON chemical_reactions(evidence_url);
