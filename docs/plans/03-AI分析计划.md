# 03 AI Analysis Plan

## 目标

对热点候选进行 AI 查询扩展和分析，输出可解释判断，并按相关性阈值决定热点状态。

## 范围

- 调用 OpenAI 兼容模型 API。
- 对关键词生成 2-5 个相关查询词。
- 输出真实性、相关性、关键词命中、重要性、摘要。
- 使用 `RELEVANCE_THRESHOLD` 将热点标记为 `active` 或 `filtered`。
- AI 调用失败时记录状态并允许任务继续。

## 输出字段

- `is_real`
- `relevance_score`
- `relevance_reason`
- `keyword_mentioned`
- `importance`
- `summary`
- `model_name`

## 验收标准

- 每条入选热点都有 AI 分析结果。
- AI 分析结果字段完整。
- AI 调用失败可追踪。
- 低相关性内容标记为 `filtered`，不发送事件邮件，不进入日报。
- 高相关性内容标记为 `active`，可进入事件邮件和日报。

## 非目标

- 不做向量库。
- 不做复杂 prompt 管理平台。
- 不做模型供应商管理后台。
