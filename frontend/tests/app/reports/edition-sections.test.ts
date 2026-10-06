import { expect, it } from "vitest";
import { editionReadingSections } from "@/app/reports/[reportId]/[key]/components/edition-sections";
import { edition } from "./edition-fixtures";

it("uses only available references in editorial order, removing duplicates and empty chapters", () => {
  const first = edition.entries[0];
  const second = { ...first, id: "second", title: "另一篇来源报道" };
  const sections = editionReadingSections({
    ...edition,
    entries: [first, second],
    highlights: ["missing"],
    themes: [],
    sections: [
      {
        label: "接口章节",
        content_ids: [second.id, "missing", first.id, second.id],
      },
    ],
    flashes: ["missing"],
  });
  expect(sections).toEqual([
    {
      id: "edition-section-1",
      title: "接口章节",
      presentation: "table",
      items: [second, first],
    },
  ]);
});

it("keeps summary-only themes and gives duplicate or unusual headings separate stable anchors", () => {
  const input = {
    ...edition,
    highlights: [],
    sections: [],
    themes: [
      { heading: "相同标题 <script>", summary: "仅摘要", content_ids: [] },
      {
        heading: "相同标题 <script>",
        summary: "",
        content_ids: [edition.entries[0].id],
      },
      { heading: "空主题", summary: "  ", content_ids: ["missing"] },
    ],
  };
  const sections = editionReadingSections(input);
  expect(sections.map(({ id, title }) => ({ id, title }))).toEqual([
    { id: "edition-theme-1", title: "相同标题 <script>" },
    { id: "edition-theme-2", title: "相同标题 <script>" },
  ]);
  expect(editionReadingSections(input)).toEqual(sections);
  expect(sections[0].summary).toBe("仅摘要");
});
