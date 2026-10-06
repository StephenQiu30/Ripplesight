import * as UI from "@/components/ui/content";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import type { Metadata } from "next";
import { connection } from "next/server";
import { ReportDetail } from "@/app/reports/[reportId]/components/report-detail";
import { getPublicEdition } from "@/api/gongkaifabu";
import {
  getPublicEditionNavigation,
  listPublicEditionCatalogue,
} from "@/api/gongkaikanwumulu";
import { EditionFailure } from "./components/edition-state";
import { PublicEditionReader } from "./[key]/components/public-edition-reader";
const labels = { daily: "日报", weekly: "周报", monthly: "月报" } as const;
type Parameters = { params: Promise<{ reportId: string }> };
function publicKind(value: string) {
  return value === "daily" || value === "weekly" || value === "monthly"
    ? value
    : null;
}
export async function generateMetadata({
  params,
}: Parameters): Promise<Metadata> {
  const kind = publicKind((await params).reportId);
  if (!kind)
    return { title: "个人报告详情", robots: { index: false, follow: false } };
  try {
    const page = await listPublicEditionCatalogue({ kind, limit: 1 });
    if (!page.entries.length)
      return {
        title: `最新${labels[kind]}`,
        robots: { index: false, follow: false },
      };
    const edition = await getPublicEdition({ kind, key: page.entries[0].key });
    return {
      title: edition.title,
      description: edition.lead,
      alternates: { canonical: edition.canonical_url ?? undefined },
      robots: { index: false, follow: false },
      openGraph: {
        title: edition.title,
        description: edition.lead,
        images: edition.canonical_url
          ? [
              new URL(
                `/og/reports/${kind}/${edition.key}.png`,
                edition.canonical_url,
              ).href,
            ]
          : undefined,
      },
    };
  } catch {
    return {
      title: `最新${labels[kind]}`,
      robots: { index: false, follow: false },
    };
  }
}
export default async function ReportDetailPage({ params }: Parameters) {
  const { reportId } = await params,
    kind = publicKind(reportId);
  if (!kind) return <ReportDetail reportId={reportId} />;
  await connection();
  let edition: HotKeyAPI.PublicEditionView | null = null;
  let navigation: HotKeyAPI.PublicEditionNavigationView | undefined;
  let catalogue: HotKeyAPI.PublicEditionCatalogueView;
  let navigationError: unknown;
  try {
    catalogue = await listPublicEditionCatalogue({ kind, limit: 6 });
    if (catalogue.entries.length) {
      const key = catalogue.entries[0].key;
      const [content, neighbours] = await Promise.allSettled([
        getPublicEdition({ kind, key }),
        getPublicEditionNavigation({ kind, key }),
      ]);
      if (content.status === "rejected") throw content.reason;
      edition = content.value;
      if (neighbours.status === "fulfilled") navigation = neighbours.value;
      else navigationError = neighbours.reason;
    }
  } catch (error) {
    return (
      <>
        <EditionFailure error={error} href={`/reports/${kind}`} />
      </>
    );
  }
  if (!edition)
    return (
      <>
        <PageState
          state="empty"
          eyebrow={`最新${labels[kind]}`}
          title="暂无刊物"
          description={`当前还没有可公开的${labels[kind]}。`}
          action={
            <Button asChild variant="outline">
              <UI.TextLink href={`/reports/${kind}/archive`}>
                读取刊物历史
              </UI.TextLink>
            </Button>
          }
        />
      </>
    );
  return (
    <>
      <PublicEditionReader
        edition={edition}
        navigation={navigation}
        catalogue={catalogue}
        navigationError={navigationError}
      />
    </>
  );
}
