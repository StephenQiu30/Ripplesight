## 1. 规格与设计收敛

- [x] 1.1 完成 proposal、design、specs 与任务定义的闭环

## 2. 事件发现实现

- [x] 2.1 优化 `backend/core/domain/hotspot_rules.py` 的聚类规则，支持近似标题聚类
- [x] 2.2 调整 `score_hotspot_event` 与排序策略，加入跨源证据约束

## 3. 测试与回归

- [x] 3.1 补充 `tests/test_hotspot_discovery.py` 的聚类与评分场景测试
- [x] 3.2 执行阶段 3 相关回归命令，确认单元测试与链路测试通过

## 4. 文档与验收同步

- [x] 4.1 更新 `docs/product/plan.md` 阶段 3 交付状态
- [x] 4.2 更新 `docs/engineering/acceptance.md` 阶段 3 验收项为已达标
