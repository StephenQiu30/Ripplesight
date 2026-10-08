---
type: record
title: PageContainer 全局内容区修复
summary: 固定位置栏与正文滚动边界已接入全站；桌面和390px实测，完整状态与审查待补
capability: capabilities/02-关键词热点.md
criterion: 统一内容容器，长内容不推动导航或覆盖页脚，键盘与阅读定位兼容
result: 未通过
date: 2026-10-07
updated: 2026-10-07
---

# PageContainer 全局内容区修复

## 做了什么

用户要求参考 Ant Design Pro PageContainer，把固定内容区作为 layout 的一部分。参考[ProLayout 的布局边界](https://procomponents.ant.design/components/layout/)与[shadcn Sidebar 的组合方式](https://ui.shadcn.com/docs/components/radix/sidebar)，复用项目现有组件；未引入另一套组件库。

`BasicLayout` 统一挂载 `src/layout/page-container.tsx`，覆盖所有路由。PageContainer 的 header / children / footer 插槽分别容纳固定位置栏、正文与页脚；登录页省略位置栏。正文占满剩余高度，横向宽度与位置栏共用 LayoutContainer，首页保留现有无额外边距的阅读布局。唯一 main 保留，`#page-content` 成为唯一正文滚动区，阅读进度、路由切换和跳到正文共用其引用。外层使用 overflow-clip，阻止聚焦时浏览器隐式滚动外壳；正文内定位元素不再越过滚动边界。打印恢复自然文档流。

## 结果

- Web 全量 120 个文件、955 项测试通过；滚动边界末次修正后，布局与阅读进度 66 项回归通过。lint、类型、格式与生产构建检查见本机 `.tools/page-container/` 日志。
- 桌面真实主题包含已入库帖子。PageDown 后正文 scrollTop 为 804，文档与 main 的 scrollTop 均为 0，位置栏 top 保持 0；侧栏折叠/恢复可用，页面没有横向溢出。
- 390 × 844 下正文 top=105、bottom=780，底部导航 top=780、bottom=844；正文内部 scrollWidth 与 clientWidth 均为 360，页面宽度为 390。End 可读到页脚，页脚 bottom=779.75，位置栏 top 保持 56，main 不滚动。Home 返回顶部，移动导航仍可见。
- 正常、加载与告警空态已在真实页面核对；四类 PageState 的容器与阅读定位还有自动化回归。错误/无权限的桌面与窄屏完整浏览器矩阵尚未完成，不能用单测代替。
- 后续检查遇到本机 Docker Desktop 停止，8666 断开。用户确认主动停止并要求保持停止、只完成代码检查；已停止恢复尝试并恢复浏览器默认视口，剩余真实页面验证不再执行。不把浏览器连接失败记作页面错误态通过。
- 文档 25 项工具测试与类型检查通过，45 页静态正文、原文和检索索引构建通过；这只证明文档有效，不替代页面验收。
- Claude CLI 审查已尝试，返回登录过期，没有取得审查结果。故本记录尚不满足工程规范的完整验收门槛。本轮不改 API、数据库、采集逻辑或账户凭据；未提交、未推送。

## 怎么复核

打开本机工作台，使用 PageDown / End / Home 检查正文滚动；折叠与展开侧栏；在 390px 下确认顶部位置栏与底部导航固定、正文可滚到页脚。切换页面应回到正文顶部，文章阅读页仍可恢复本机阅读位置。正常、空、加载、错误与无权限使用各页面原有状态，不能通过伪造业务数据证明真实业务可用。

桌面及窄屏截图分别保存于本机忽略目录 `.tools/page-container/desktop.jpg` 和 `mobile.jpg`；不进入公开文档产物。实际进度以 BACKLOG 当前页面容器修复条目为准。
