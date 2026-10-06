import { publicItem } from "../components/home-fixtures";

export const editionEntry = (
  key: string,
): HotKeyAPI.PublicEditionIndexView => ({
  kind: "daily",
  key,
  title: `刊物 ${key}`,
  revision: 2,
  created_at: "2026-10-06T00:00:00Z",
  reading_url: `/reports/daily/${key}`,
});

export const edition: HotKeyAPI.PublicEditionView = {
  id: "edition-1",
  kind: "daily",
  key: "2026-10-06",
  revision: 2,
  title: "真实接口刊物测试",
  lead: "本期导语。",
  window_start: "2026-10-05T00:00:00Z",
  window_end: "2026-10-06T00:00:00Z",
  created_at: "2026-10-06T00:00:00Z",
  highlights: [publicItem.id],
  themes: [
    {
      heading: "重点事件",
      summary: "已有的主题摘要。",
      content_ids: [publicItem.id],
    },
  ],
  sections: [{ label: "今日社媒热点", content_ids: [publicItem.id] }],
  flashes: [],
  entries: [publicItem],
  metrics: { selected_count: 1 },
  body_markdown: "",
  canonical_url: null,
};
