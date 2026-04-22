# AI 热点平台技术方案

## 1. 技术方案概述

本技术方案承接已确认的产品目标，不重新定义产品范围，重点回答“系统如何实现”。

## 2. 已确认技术选型

| 层级 | 选型 | 理由 |
| --- | --- | --- |
| 前端 | `Next.js + TypeScript` | 适合控制台、搜索页、详情页 |
| 后端 | `Python + FastAPI` | 适合采集、NLP、聚类与 LLM 编排 |
| 数据库 | `PostgreSQL` | 关系数据、全文检索和后续向量能力兼顾 |
| 异步任务 | `Celery + Redis` | 适合定时任务、异步执行、失败重试 |
| 模型服务 | `OpenAI API` | 适合结构化输出、摘要、分类与翻译 |
| 邮件 | `Resend` | 适合快速打通日报投递闭环 |
| 部署 | `Docker 自托管` | 适合内部使用与成本控制 |
| 接口方法 | `OpenAPI First` | 先定契约再实现 |
| 代码组织 | `分层模块化` | 适合后续长期演进 |

## 3. 工程设计原则

- 业务逻辑与框架装配分离
- 契约先行，避免接口随意膨胀
- 外部依赖必须通过适配器接入
- 所有热点结果必须保留来源追踪链路
- 单个来源失败不能阻塞整体日报链路

## 4. 目录职责

- `services/api`
  - 仅承载 `FastAPI` 启动、装配、路由挂载
- `services/worker`
  - 仅承载 `Celery` worker 和定时任务入口
- `backend/core`
  - 共享后端业务逻辑
- `frontend/web`
  - 控制台展示与交互
- `contracts/openapi`
  - OpenAPI 契约基线
- `infra`
  - Docker Compose 与环境变量模板

## 5. 分层模块化设计

### 5.1 domain

- 热点事件模型
- 来源规则
- 聚类规则
- 评分规则

### 5.2 application

- 采集编排
- 去重与聚类编排
- 摘要编排
- 日报生成编排
- 推送编排

### 5.3 infrastructure

- X API 适配器
- NewsAPI 适配器
- GDELT 适配器
- RSS / RSSHub 适配器
- GitHub / Hacker News / Product Hunt / Hugging Face 适配器
- PostgreSQL、Redis、Resend 接入

### 5.4 interface

- DTO
- 错误响应结构
- 分页结构
- 过滤条件对象

## 6. 系统架构与数据流

### 6.1 总体流程

1. 调度系统触发采集
2. 多来源拉取原始内容
3. 标准化并写入原始内容层
4. 执行去重与事件聚类
5. 计算热点分数
6. 调用模型生成摘要与标签
7. 编排日报并发送邮件
8. 控制台展示热点和详情

### 6.2 数据流

- 采集流：`SourceConfig -> Adapter -> RawContentItem`
- 分析流：`RawContentItem -> Dedup -> Cluster -> HotspotEvent`
- 摘要流：`HotspotEvent -> LLM -> DailyDigest`
- 展示流：`HotspotEvent / DailyDigest -> API -> Web`
- 推送流：`DailyDigest -> Resend`

## 7. 核心数据模型

### 7.1 SourceConfig

- `id`
- `name`
- `source_type`
- `access_method`
- `language`
- `region`
- `weight`
- `poll_interval_minutes`
- `enabled`

### 7.2 KeywordRule

- `id`
- `keyword`
- `category`
- `query_template`
- `priority`
- `enabled`

### 7.3 MonitoredAccount

- `id`
- `platform`
- `handle`
- `display_name`
- `account_type`
- `weight`
- `enabled`

### 7.4 RawContentItem

- `id`
- `source_config_id`
- `external_id`
- `title`
- `content_excerpt`
- `url`
- `author`
- `published_at`
- `language`
- `raw_payload`
- `ingested_at`

### 7.5 HotspotEvent

- `id`
- `event_title`
- `summary_zh`
- `topic_tags`
- `score`
- `status`
- `first_seen_at`
- `last_seen_at`
- `source_count`
- `evidence_links`

### 7.6 DailyDigest

- `id`
- `digest_date`
- `title`
- `highlights`
- `event_ids`
- `generated_at`
- `delivery_status`

### 7.7 FeedbackRecord

- `id`
- `target_type`
- `target_id`
- `feedback_type`
- `comment`
- `created_at`

## 8. API 边界

第一阶段接口固定为：

- `/api/sources`
- `/api/x/keywords`
- `/api/x/accounts`
- `/api/events`
- `/api/events/{id}`
- `/api/digests/today`
- `/api/search`
- `/api/feedback`

统一要求：

- 列表接口统一分页结构
- 时间字段统一 ISO 8601
- 错误返回统一结构
- 不暴露底层抓取细节

## 9. X 数据源专项实现

### 9.1 接入原则

- 仅使用官方 X API
- X 是核心来源之一，但不是唯一热点判断依据
- X 数据进入总榜前必须经过统一治理

### 9.2 三条链路

#### 关键词搜索

- 使用 `Recent Search`
- 默认最近 7 天窗口
- 支持品牌词、模型词、事件词、行业词

#### 重点账号监测

- 监测 AI 公司官方账号、创始人、研究负责人、关键 KOL
- 用于识别一手消息和权威信号

#### 趋势词监测

- 使用 `Trends by WOEID`
- 监控全球与重点地区趋势
- 对 AI 相关趋势词进行二次搜索和归因

### 9.3 处理流程

X 数据统一经历：

1. 标准化
2. 去重
3. 降噪
4. 聚类
5. 评分
6. 摘要
7. 证据回链

### 9.4 边界限制

- `Recent Search` 默认只覆盖最近 7 天
- `Filtered Stream` 负责近实时能力
- 更长历史和更大规模能力不是 v1 前提
- 必须单独监控 X API 配额和成本
- 第三方抓取仅作为未来备选方案

## 10. 非功能性要求

### 10.1 可维护性

- 接口、数据模型、错误结构统一
- 规则可配置，不在多个位置硬编码

### 10.2 可追溯性

- 每条热点必须能追溯到原始来源
- 每条摘要必须记录来源与生成时间

### 10.3 稳定性

- 单个来源失败不阻塞整体日报
- 外部 API 异常应具备降级路径

### 10.4 成本控制

- 支持按来源、任务和模型调用观察成本
- 高成本任务应支持优先级裁剪

### 10.5 合规与版权

- 尊重来源条款、robots 和速率限制
- 不默认长期保存完整第三方正文
- 优先保存元数据、摘要、链接和必要片段
