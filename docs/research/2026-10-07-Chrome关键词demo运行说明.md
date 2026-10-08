---
type: research
title: Chrome 关键词 demo 运行说明
summary: 复用本机 Chrome 登录的 B 站真实采集、结果页、小时调度与停止恢复操作
status: 真实与定时实采通过，长期运行与评论增量待观察
date: 2026-10-07
updated: 2026-10-07
---

# Chrome 关键词 demo 运行说明

需求仍以[总 PRD](../product/prd/01-PRD.md)为准，执行范围见[首平台验证卡](2026-10-07-国内平台关键词监控POC验证.md)，进度仅维护在 [BACKLOG](../../BACKLOG.md)。这是一份可复跑操作说明，不是新的产品需求。

## 当前入口与边界

- 本机结果页：[关键词 demo](http://127.0.0.1:8669/)。每 30 秒刷新，列出来源、发布时间、首见/最近采集、评论与每轮证据。
- 查询为 `DeepSeek`，平台 B 站；`深度求索` 是可替换示例，当前没有同时运行别名查询。相关性采用标题/摘要包含规则，不是语义相似度模型。
- 每次搜索只取最近 72 小时的第一页（最多 5 条候选），按来源最新排序；保留其中前 2 条命中，分别取一页最多 20 条根评论。无楼中楼或全量覆盖承诺。
- 采集间隔 1 小时，北京时间 00:00–08:00 静默；每轮最多 4 次来源请求，单个 demo 每日上限 60。不要并行复制多个 demo 放大账号请求量。
- Chrome 和现有 Framefetch 身份扩展需保持可用，本机 cookie-source 版本 1.3.3、监听 `127.0.0.1:19101`；启动前已确认扩展连接。只请求 B 站域 Cookie，每轮重新读取，只在内存中使用。接口和代理费用均为 0。
- 本轮新增独立的有界 HTTP 适配器，不执行或修改外部 MediaCrawler checkout；外部差异局限于来源适配器，输出复用既有 SourcePost/SourceComment。
- 数据在主仓库 `.tools/keyword-demo/deepseek/`，目录 0700、状态 0600、被 Git 忽略；保留 30 天，按平台 ID 去重。本机结果页只绑定 loopback，不上传到知识库或公开站点。
- 独立 demo 不写业务数据库，不消费既有积压 Job；正式接管现状见文末。国内其他平台、语义模型与长期稳定性仍未验收。

## 复跑与配置

在 `ripplesight-server/backend` 执行：

```sh
PYTHONPATH=app uv run python -m cli.keyword_demo \
  --identity-env "$HOME/Library/Application Support/Framefetch/identity.env" \
  --directory ../.tools/keyword-demo/deepseek --keyword DeepSeek
```

命令检查持久化到期时间；未到期不会发出来源请求。`--watch` 每 30 秒检查一次，同样只在小时到期时采集。当前已有 LaunchAgent，不要同时再启动 watch。关键词用 `--keyword` 配置；同一目录拒绝改变关键词，需先停掉旧任务再使用新目录，避免混合证据和重复调度。依赖使用仓库 `uv.lock`，不需要任何收费采集 Key。

已安装的本机调度为 `com.ripplesight.keyword-demo`，每 60 秒检查是否到期；首次安装时尝试把日志放在 Desktop，被 macOS 拒绝，随后将日志改为 `~/Library/Application Support/Ripplesight/`，未关闭系统保护。预览服务为 `com.ripplesight.keyword-demo-preview`。两份本机 plist 在 `~/Library/LaunchAgents/`，不包含 token；采集 token 只引用已有私有 identity.env。

```sh
# 检查运行次数和退出状态（不会输出 Cookie）
launchctl print "gui/$(id -u)/com.ripplesight.keyword-demo"
# 停止采集调度，保留结果
launchctl bootout "gui/$(id -u)/com.ripplesight.keyword-demo"
# 恢复调度
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.ripplesight.keyword-demo.plist"
# 停止本机预览
launchctl bootout "gui/$(id -u)/com.ripplesight.keyword-demo-preview"
```

也可在上述 Python 命令后加 `--pause` 暂停来源请求。遇到登录失效、风控、桥接失联或进程中断，会持久化暂停原因；正常轮询不自动重试。本人在 Chrome 完成必要恢复后，显式运行带 `--resume` 的同一命令；它仍尊重已有下一次到期时间。不要删除 state.json 来绕过预算或停止状态。

## 按 pm-execution 的验收场景

角色均为本机主题跟踪者。固定样本测试不访问外网，真实数据验收使用本人已授权的 Chrome 会话。

| 场景 / 目标 | 起始条件 | 操作 | 预期与证据 |
|---|---|---|---|
| 真实帖子 | Chrome B 站已登录、桥接连通 | 执行到期任务，打开结果页和原文 | 平台 ID、72h 半开时间窗、发布时间/采集时间可核对；真实结果见验收记录 |
| 自动调度 | LaunchAgent 已加载 | 等待后台检查，观察最近调度时间与日志 | 非人工触发的检查时间增长；到期后生成新轮次。本次两分钟到期的自动轮次已实采成功；连续小时稳定性另行观察 |
| 去重与新窗口 | 已保存首轮固定样本 | 未到期 tick，再到期 tick，包含窗口右端样本 | 未到期零请求；重复 ID 不新增，新的窗口内容可新增 |
| 真实评论 | 来源存在可访问评论 | 随每个入选帖读取新评论页 | 保存原始根评论与原文链接；本轮空列表只证明空响应，不证明真实非空评论/增量 |
| 登录/限流 | 固定失效会话或 -352 响应 | 执行，再触发未来 tick | 立即停止，后续零请求，无换号、代理或重试 |
| 中断/预算 | 已有 running 状态或日预算用尽 | 重启检查 | 中断进入暂停；预算用尽顺延到次日，持久化不重置 |
| 阅读安全 | 固定恶意 HTML 文本 | 生成结果页并展开评论 | 仅显示转义文本，Cookie 不在产物中 |

相关测试位于 `backend/tests/unit/sources/test_keyword_demo.py`；日志不包括平台响应原文或账号凭据。真实帖子标题仅为来源陈述，不代表对内容真实性的背书。


## 接入正式前后端

最新用户指令要求 demo 跑通后接入工作台。本轮接入沿用同一个 `bilibili` 来源；原生 Chrome 路径使用固定 API 地址，旧 MediaCrawler 路径保持兼容。搜索和评论分别进入现有任务系统，数据只进入 PostgreSQL；源码验证与真实验收见[接入验收记录](../records/2026-10-07-Chrome工作台接入验收.md)。

接管前提：确认现有 Ripplesight 用户名对应的账号 UUID，在根目录私有 `.env` 设置 `HOTKEY_BILIBILI_CHROME_OWNER_ID`，并重新创建 API 容器以加载配置。仅此 UUID 可以启用与运行本机 Chrome 来源。无需新建账号，不修改密码或导出 Cookie；本机桥接身份文件保留原有私有权限。数据库结构不变，无需迁移或导入 demo JSON。

1. 登录 [来源设置](http://127.0.0.1:8666/sources)，点击“启用 Chrome 采集”。服务端保存来源政策、30 天留存和每日 60 次来源请求预算；若账号没有全局请求预算，初始化每日 60 次，已有预算不覆盖。
2. 创建 `DeepSeek` 主题，选择 B 站、每小时，关闭周报与邮件投递。本轮宿主不执行日报生成。启用关注后可选择“立即采集”，或由到期日程受理。首版每轮只执行一个查询；多词规则中的上游检索只用首个分片，其余本地规则仍生效。
3. 在仓库 `backend/` 执行 `PYTHONPATH=app uv run python -m worker.chrome`。该宿主入口读取根 `.env`，将 Compose 的数据库宿主别名映射到本机回环地址，只处理绑定账号的 B 站搜索/评论与到期日程；不启动其他账号或来源历史任务。它复用原有 outbox、租约、预算和执行器，每轮最多两批各四条投递。它与标准 Worker 二选一部署；不要同时启动两种 Worker。
4. 在主题页“最新监控结果”查看最近 5 条资料，打开作品读取已采集根评论、时间与原文。页面每 30 秒刷新本地结果，不会因刷新页面触发平台请求。任务/覆盖页如实显示部分覆盖，相关性暂用关键词规则，语义判断未验收。
5. 单轮真实验收后，停用旧 `com.ripplesight.keyword-demo` 的采集调度，保留 8669 的证据预览；再用本机服务管理器每 60 秒调用上述宿主入口。主题和来源的持久化频率限制使实际平台采集保持每小时，00:00–08:00 静默。接管当天须核对旧 demo 已用请求量并从正式可用预算中扣除，避免两份计数叠加突破账号每日上限。首次自动到期实采完成后才能标记接管成功。

搜索每次最多 2 次平台请求（登录检查与搜索），每个评论任务最多 2 次（登录检查与重新取样），同一账号的所有 B 站任务共享每日预算。根评论只跟踪当日已发现的至多两帖/主题；评论数未知不会当成 0 跳过。遇到登录失效或风控会把来源持久暂停；须在来源设置核对停止原因并勾选本人确认后恢复，普通启用按钮不能绕过暂停。

当前接管结果见下方记录。机器睡眠、Chrome/扩展退出和本机服务不可用会影响定时执行；本轮不承诺全天在线。


### 当前本机接管状态

2026-10-07 20:09 已用当前 Chrome 中登录的 Ripplesight 账号启用正式来源，主题 `72ba2ae0-0ba5-4f41-bee1-6da6210398df` 已设为每小时；首次入库 2 帖，根评论 0。旧 `com.ripplesight.keyword-demo` 已卸载运行，预览仍保留；不要同时重新启动两个采集器。旧当日 22 次请求已通过正式预算预留和结算承接。

正式 LaunchAgent 为 `~/Library/LaunchAgents/com.ripplesight.chrome-monitor.plist`，每 60 秒执行 `worker.chrome`，由数据库小时日程决定是否采集。日志在 `~/Library/Application Support/Ripplesight/chrome-monitor*.log`。暂停优先用工作台暂停主题/来源；完全停止宿主轮询执行 `launchctl bootout gui/$(id -u)/com.ripplesight.chrome-monitor`。不得再同时启动全局 Worker。本轮未运行报告生成或发送邮件。
