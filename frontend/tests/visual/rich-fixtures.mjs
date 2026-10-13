// Fictional display samples, consumed only by the loopback visual fixture API.
// Keep unknown contract fields unknown; never inject markup or production data.
export function richFixtures({
  publicItem,
  publicStory,
  edition,
  board,
  topic,
}) {
  const titles = [
    "开源推理模型发布新版本，社区开始验证长上下文与工具调用能力",
    "小型多模态模型进入端侧设备：从离线识别到本地语音交互的应用观察",
    "研究团队提出新的检索评测方法，比较复杂问题中的证据覆盖与引用准确性",
    "开发工具周报：代码助手、自动化测试与团队知识库的最新进展",
    "从原型到实际部署：企业如何评估推理成本、数据边界与模型可靠性——一份包含多语言 Mixed Language 和超长标题的展示样本",
    "新论文：稀疏注意力在长文档理解中的表现与局限",
    "社区讨论：智能体执行失败后，应该如何恢复和解释中间状态？",
    "产品更新：将结构化搜索与来源引用带入日常信息阅读",
    "公开数据集发布，覆盖中文问答、图表理解和多轮对话",
    "本周值得关注的研究与工程实践",
  ];
  const summaries = [
    "（演示数据）团队公开了模型权重、评测方法与部署说明。来自不同社区的讨论关注推理能力、使用成本和可复现性；这些内容仅用于检查页面的视觉密度。",
    "（演示数据）轻量模型将部分任务放到本地执行，应用场景包含图像理解、语音交互和离线检索。",
    "（演示数据）这是一条较长的摘要，用于检查多行文本的行高、折行、分隔线与后续操作按钮之间的距离。评测覆盖开放问答和复杂信息综合，同时保留尚未证实的结果与局限，避免将样本当成真实新闻。",
  ];
  const sources = ["模型实验室", "技术社区", "研究通讯", "开发者周刊"];
  const items = titles.map((title, index) => {
    const id = `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`;
    return {
      ...publicItem,
      id,
      title: `${title}（演示）`,
      summary: summaries[index % summaries.length],
      reading_url: `/items/${id}`,
      original_url: `https://example.com/visual-demo/${index + 1}`,
      published_at: `2026-10-12T${String(8 + (index % 4)).padStart(2, "0")}:00:00Z`,
      discovered_at: "2026-10-12T12:00:00Z",
      timeline_at: "2026-10-12T12:00:00Z",
      backfill: false,
      selected: index < 4,
      category: index % 2 === 0 ? "paper" : "industry",
      tags:
        index % 2 === 0 ? ["人工智能", "开源", "研究"] : ["产品", "工程实践"],
      source: {
        ...publicItem.source,
        key: `visual-source-${index % sources.length}`,
        name: `${sources[index % sources.length]}（演示）`,
      },
    };
  });
  const stories = [
    "开源推理模型引发开发者关注，评测结果与实际应用持续更新（演示）",
    "端侧智能进入新阶段，多模态体验成为产品讨论焦点（演示）",
    "模型评测方法出现新讨论：如何让排名反映真实任务表现（演示）",
  ].map((title, index) => ({
    ...publicStory,
    id: index === 0 ? "story-1" : `story-${index + 1}`,
    title,
    summary: summaries[index],
    latest_progress:
      "（演示数据）社区新增复现记录，团队补充了部署说明；长期表现仍需观察。",
    first_seen_at: "2026-10-11T08:00:00Z",
    heat: 12840 - index * 2900,
    attention: {
      ...publicStory.attention,
      heat: 12840 - index * 2900,
      previous_heat: 9800 - index * 2200,
      window_end: "2026-10-12T12:00:00Z",
      last_source_time: "2026-10-12T11:00:00Z",
    },
    reports: items.slice(index, index + 5),
  }));
  const developments = [
    "团队发布模型与技术说明（演示）",
    "社区开始复现评测并整理差异（演示）",
    "新增部署教程与实际应用反馈（演示）",
    "团队回应已知限制并更新文档（演示）",
  ].map((title, index) => ({
    fact_id: `visual-fact-${index + 1}`,
    title,
    anchor_at: `2026-10-12T${String(8 + index).padStart(2, "0")}:00:00Z`,
    report_count: index + 2,
    representative: items[index],
  }));
  const topics = [
    "开源模型与推理能力（演示）",
    "智能体与开发工具（演示）",
    "端侧多模态与交互体验的长期观察（演示）",
    "研究论文与评测方法（演示）",
    "企业产品动态（演示）",
    "中文数据集与应用（演示）",
  ].map((name, index) => ({
    ...topic,
    id: index === 0 ? "visual-topic" : `visual-topic-${index + 1}`,
    name,
    status: index === 3 ? "paused" : "active",
    rules: {
      match_any: ["开源", "大模型", "推理", "模型评测", "工具调用"].slice(
        0,
        index === 0 ? 5 : 2,
      ),
      match_all: index === 0 ? ["人工智能"] : [],
      exclude: index === 0 ? ["广告", "招聘"] : [],
    },
  }));
  const richEdition = {
    ...edition,
    key: "2026-10-12",
    window_start: "2026-10-11T12:00:00Z",
    window_end: "2026-10-12T12:00:00Z",
    created_at: "2026-10-12T12:00:00Z",
    title: "知微日报：模型、研究与产品的一日观察（演示）",
    lead: "（演示数据）今天关注开源推理、端侧多模态与开发工具。下面的分组、摘要和来源均为隔离的视觉样本，用于检查长页面阅读节奏。",
    highlights: items.slice(0, 3).map((item) => item.id),
    themes: [
      {
        heading: "模型与研究",
        summary: summaries[0],
        content_ids: items.slice(0, 3).map((item) => item.id),
      },
      {
        heading: "工具与应用",
        summary: summaries[1],
        content_ids: items.slice(3, 6).map((item) => item.id),
      },
    ],
    sections: [
      {
        label: "模型与研究",
        content_ids: items.slice(0, 3).map((item) => item.id),
      },
      {
        label: "开发工具与产品",
        content_ids: items.slice(3, 6).map((item) => item.id),
      },
      {
        label: "社区与行业",
        content_ids: items.slice(6, 9).map((item) => item.id),
      },
    ],
    flashes: [items[9].id],
    entries: items,
    metrics: { ...edition.metrics, selected_count: items.length },
  };
  const entries = Array.from({ length: 12 }, (_, index) => ({
    ...board.entries[0],
    rank: index + 1,
    score: Math.round((94.6 - index * 2.7) * 10) / 10,
    model: {
      ...board.entries[0].model,
      slug: `visual-model-${index + 1}`,
      name: `${["Aurora", "Ripple", "Orion", "Cedar"][index % 4]} ${index + 1}${index === 4 ? " Long Context Research Preview" : ""}（演示）`,
      provider: `${["晨光实验室", "开源研究组", "星河团队"][index % 3]}（演示）`,
      brand: { src: null, monogram: "ARO"[index % 3] },
    },
    coverage: 0.95 - index * 0.03,
    confidence: "LOW",
    stability: {
      ...board.entries[0].stability,
      from_rank: Math.max(1, index),
      to_rank: Math.min(12, index + 3),
      fixed_from: Math.max(1, index),
      fixed_to: Math.min(12, index + 3),
      ordinal_rank: index + 1,
    },
  }));
  return {
    items,
    stories,
    developments,
    topics,
    edition: richEdition,
    board: { ...board, entries, filter_entries: entries },
  };
}
