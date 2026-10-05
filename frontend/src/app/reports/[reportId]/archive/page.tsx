import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import {
  getPublicDailyCalendar,
  listPublicEditionCatalogue,
} from "@/api/gongkaikanwumulu";
import { PublicEditionCatalogue } from "@/components/publication/edition-catalogue";
import { PublicationFailure } from "@/components/publication/reading-parts";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
const labels = { daily: "日报", weekly: "周报", monthly: "月报" } as const;
type Parameters = { params: Promise<{ reportId: string }> };
function kind(value: string) {
  if (value !== "daily" && value !== "weekly" && value !== "monthly")
    notFound();
  return value;
}
export async function generateMetadata({
  params,
}: Parameters): Promise<Metadata> {
  const current = kind((await params).reportId);
  let indexable = false;
  try {
    const page = await listPublicEditionCatalogue({ kind: current, limit: 20 });
    indexable =
      page.entries.length > 0 &&
      page.entries.every((entry) => entry.indexable === true);
  } catch {
    // Unavailable catalogue pages must not become an indexed error page.
  }
  return publicSiteMetadata({
    title: `${labels[current]}历史`,
    path: `/reports/${current}/archive`,
    imagePath: `/og/pages/${current}.png`,
    indexable,
  });
}
export default async function PublicEditionArchive({ params }: Parameters) {
  await connection();
  const current = kind((await params).reportId);
  let initial: HotKeyAPI.PublicEditionCatalogueView;
  let calendar: HotKeyAPI.PublicDailyCalendarView | undefined;
  try {
    initial = await listPublicEditionCatalogue({ kind: current, limit: 20 });
    const month =
      initial.entries[0]?.key.slice(0, 7) ??
      new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" })
        .format(new Date())
        .slice(0, 7);
    calendar =
      current === "daily" ? await getPublicDailyCalendar({ month }) : undefined;
  } catch (error) {
    return (
      <>
        <PublicationFailure
          error={error}
          href={`/reports/${current}/archive`}
        />
      </>
    );
  }
  return (
    <>
      <PublicEditionCatalogue initial={initial} initialCalendar={calendar} />
    </>
  );
}
