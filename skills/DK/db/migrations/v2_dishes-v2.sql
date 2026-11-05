
-- dishes
ALTER TABLE dishes ADD COLUMN evidence_url TEXT;
ALTER TABLE dishes ADD COLUMN health_warnings TEXT;

-- dish_versions
ALTER TABLE dish_versions ADD COLUMN evidence_url TEXT;
ALTER TABLE dish_versions ADD COLUMN health_warnings TEXT;

-- dish_ingredients
ALTER TABLE dish_ingredients ADD COLUMN evidence_url TEXT;
ALTER TABLE dish_ingredients ADD COLUMN health_warnings TEXT;

-- dish_steps
-- 已有 common_mistakes,加 evidence_url 即可
ALTER TABLE dish_steps ADD COLUMN evidence_url TEXT;

-- 索引
CREATE INDEX IF NOT EXISTS idx_evidence_url_dishes ON dishes(evidence_url);

