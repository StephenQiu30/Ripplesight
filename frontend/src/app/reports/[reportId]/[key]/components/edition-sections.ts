export type EditionReadingSection = {
  id: string;
  title: string;
  summary?: string;
  items: HotKeyAPI.PublicItemView[];
  presentation: "events" | "table";
};

/** The same sections drive the body and its outline; missing references never become rows. */
export function editionReadingSections(
  edition: HotKeyAPI.PublicEditionView,
): EditionReadingSection[] {
  const entries = new Map(edition.entries.map((entry) => [entry.id, entry]));
  const references = (ids: string[]) =>
    [...new Set(ids)].flatMap((id) => {
      const entry = entries.get(id);
      return entry ? [entry] : [];
    });
  const sections: EditionReadingSection[] = [
    {
      id: "edition-highlights",
      title: "今日要点",
      items: references(edition.highlights),
      presentation: "events",
    },
    ...edition.themes.map((theme, index) => ({
      id: `edition-theme-${index + 1}`,
      title: theme.heading,
      summary: theme.summary,
      items: references(theme.content_ids),
      presentation: "events" as const,
    })),
    ...edition.sections.map((section, index) => ({
      id: `edition-section-${index + 1}`,
      title: section.label,
      items: references(section.content_ids),
      presentation: "table" as const,
    })),
    {
      id: "edition-flashes",
      title: "更多动态",
      items: references(edition.flashes),
      presentation: "table",
    },
  ];
  return sections.filter(
    (section) => section.items.length || section.summary?.trim(),
  );
}
