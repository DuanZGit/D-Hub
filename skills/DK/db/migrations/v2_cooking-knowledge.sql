
-- cooking_methods
ALTER TABLE cooking_methods ADD COLUMN evidence_url TEXT;
ALTER TABLE cooking_methods ADD COLUMN health_warnings TEXT;

-- cookware
ALTER TABLE cookware ADD COLUMN evidence_url TEXT;
-- cookware 已有 safety_note,不再加 health_warnings

-- ingredient_prep
ALTER TABLE ingredient_prep ADD COLUMN evidence_url TEXT;
-- ingredient_prep 没有 health_note 概念,加 health_warnings
ALTER TABLE ingredient_prep ADD COLUMN health_warnings TEXT;

-- seasoning_science
ALTER TABLE seasoning_science ADD COLUMN evidence_url TEXT;
-- 已有 health_note

-- baking_knowledge
ALTER TABLE baking_knowledge ADD COLUMN evidence_url TEXT;
ALTER TABLE baking_knowledge ADD COLUMN health_warnings TEXT;

-- healthy_cooking
-- 已有 special_population,加 evidence_url 即可
ALTER TABLE healthy_cooking ADD COLUMN evidence_url TEXT;

-- cooking_faq
ALTER TABLE cooking_faq ADD COLUMN evidence_url TEXT;
ALTER TABLE cooking_faq ADD COLUMN health_warnings TEXT;

-- 索引(只为本 DB 内的表)
CREATE INDEX IF NOT EXISTS idx_evidence_url_cooking_methods ON cooking_methods(evidence_url);

