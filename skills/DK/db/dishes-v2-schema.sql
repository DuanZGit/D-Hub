CREATE TABLE dishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE dish_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dish_id INTEGER NOT NULL,
    version_name TEXT NOT NULL,      -- 如：家常版、餐厅版、减脂版、懒人版
    style TEXT,                       -- 口味：咸鲜/酸甜/麻辣/清淡
    difficulty TEXT,                  -- 难度
    time_minutes INTEGER,
    servings INTEGER,
    description TEXT, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT,
    FOREIGN KEY (dish_id) REFERENCES dishes(id)
);
CREATE TABLE dish_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    category TEXT,                    -- 主料/腌料/酱汁/配料
    name TEXT NOT NULL,
    amount TEXT NOT NULL,             -- 精确用量：200g、2汤匙、1/2茶匙
    unit TEXT,                        -- 单位
    optional INTEGER DEFAULT 0,      -- 是否可选
    substitute TEXT,                  -- 替代品
    prep TEXT,                        -- 预处理
    science TEXT, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT,                     -- 科学原理
    FOREIGN KEY (version_id) REFERENCES dish_versions(id)
);
CREATE TABLE dish_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    phase TEXT,                       -- 阶段：准备/腌制/烹饪/调味/收尾
    action TEXT NOT NULL,
    description TEXT NOT NULL,
    duration TEXT,
    temperature TEXT,
    visual TEXT,                      -- 视觉判断标准
    science TEXT,
    tips TEXT,
    common_mistakes TEXT, source_id INTEGER, source_platform TEXT, source_title TEXT, source_url TEXT, source_method TEXT,             -- 常见错误
    FOREIGN KEY (version_id) REFERENCES dish_versions(id)
);
CREATE INDEX idx_dishes_name ON dishes(name);
CREATE INDEX idx_dish_versions_dish_id ON dish_versions(dish_id);
CREATE INDEX idx_dish_ingredients_version_id ON dish_ingredients(version_id);
CREATE INDEX idx_dish_steps_version_id ON dish_steps(version_id);
CREATE TABLE source_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  title TEXT,
  url TEXT NOT NULL,
  method TEXT,
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
