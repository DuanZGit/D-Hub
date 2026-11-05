---
name: coffee-extraction
description: 咖啡萃取追踪、设备标定与排障技能。记录参数、判断问题层级、只改一个变量，沉淀个人配方。
version: 1.0
author: Minis
tags: [coffee, espresso, grinder, troubleshooting]
license: MIT
disable-model-invocation: true
---

# 咖啡萃取追踪与排障

> 核心：**测机器 → 记录参数 → 找问题层级 → 只改一个变量 → 沉淀配方**

## 触发词
`dk 萃取` / `dk 咖啡` / `dk 磨豆机` / `dk 意式`

> **决策前置**：购机/配件/参数取舍类决策，先明确目标与预算、列出候选与权衡再定；萃取参数实验遵守"只改一个变量"。

## 工作流

```
0. 先读固定记录与未结项
   - records/duanz-coffee-log.md
   - 先结账上一杯的待验证项，再开新参数实验

1. 设备状态确认
   - 空放水量
   - 盲碗压力
   - 磨豆机零点/刻度体系
   - 粉碗容量

2. 萃取参数记录
   - 直接把用户口述追加到 records/duanz-coffee-log.md
   - 缺失字段写「未记录」，不要求用户手填
   - 豆子 + 烘焙日期/度/状态
   - 粉量 / 出液重量 / 研磨刻度
   - P1/P2 / 温度 / 压力
   - 是否无底手柄 / WDT布粉
   - 总时间 / 饮品配比 / 味道 / 喷溅

3. 问题层级判断
   - 先机器，再粉饼，再配方，再风味
   - 建压慢：先水路/设备标定，再粉饼
   - 压力高流速慢：研磨过细/粉量过多
   - 压力低流速快：研磨过粗/粉量不足/通道
   - 喷溅：结块/布粉/WDT/粉碗/密封

4. 调整建议
   - 只改一个变量
   - 说明保持不变的字段
   - 记录待验证项，不把推断写成事实

5. 沉淀配方
   - 稳定参数后先记为阶段基准
   - 至少重复两次且关键参数一致，才建议升级为已验证配方
```

## 固定文件分工

- `records/duanz-coffee-log.md`：唯一长期追加的个人咖啡记录。
- `references/measurement-template.md`：空白逐杯记录模板，不放历史数据。
- `references/recording-requirements.md`：记录要求、问题层级、公式与输出规则。
- `references/espresso-troubleshooting.md`：机器排障参考。
- `profiles/duanz-coffee-setup.md`：设备与配方摘要。

## 技能入口

```bash
dk 萃取
dk 咖啡
dk 磨豆机
dk 意式
```

## 技能层级

1. 萃取记录模板
2. 设备标定
3. 排障决策树
4. 个人配方沉淀

## 重要原则

- 机器侧永远排第一
- 只改一个变量
- 标称刻度和实际刻度分开
- 评论区经验不能替代实测
- 研磨、粉量、压力、预浸泡不要同时改

## 技能相关文件

- `references/espresso-troubleshooting.md`：常见喷溅、压力慢处理
- `references/measurement-template.md`：萃取记录模板
- `profiles/duanz-coffee-setup.md`：个人设备数据区

## 技能使用

当你输入 `dk 萃取` 或 `dk 咖啡` 时，技能会引导你完成一次完整萃取记录，并给出下次只调整一个变量的建议。
