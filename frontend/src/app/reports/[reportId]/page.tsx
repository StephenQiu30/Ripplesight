import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { ReportDetail } from "@/app/reports/[reportId]/components/report-detail";
import { getPublicEdition } from "@/api/gongkaifabu";
import {
  getPublicEditionNavigation,
  listPublicEditionCatalogue,
} from "@/api/gongkaikanwumulu";
import {
  PublicationFailure,
  PublicationNavigation,
  publicationApiOptions,
} from "@/components/publication/reading-parts";
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
    return { title: "日报详情", robots: { index: false, follow: false } };
  try {
    const page = await listPublicEditionCatalogue(
      { kind, limit: 1 },
      publicationApiOptions,
    );
    if (!page.entries.length)
      return {
        title: `最新${labels[kind]}`,
        robots: { index: false, follow: false },
      };
    const edition = await getPublicEdition(
      { kind, key: page.entries[0].key },
      publicationApiOptions,
    );
    return {
      title: edition.title,
      description: edition.lead,
      alternates: { canonical: edition.canonical_url ?? undefined },
      robots: { index: edition.indexable, follow: edition.indexable },
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
  try {
    const page = await listPublicEditionCatalogue(
      { kind, limit: 1 },
      publicationApiOptions,
    );
    if (page.entries.length) {
      const key = page.entries[0].key;
      [edition, navigation] = await Promise.all([
        getPublicEdition({ kind, key }, publicationApiOptions),
        getPublicEditionNavigation({ kind, key }, publicationApiOptions),
      ]);
    }
  } catch (error) {
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure error={error} href={`/reports/${kind}`} />
      </>
    );
  }
  if (!edition)
    return (
      <>
        <PublicationNavigation />
        <main className="mx-auto max-w-4xl space-y-5 px-5 py-10">
          <h1 className="text-3xl font-medium">最新{labels[kind]}</h1>
          <p>当前还没有可公开的{labels[kind]}。</p>
          <Link href={`/reports/${kind}/archive`} className="underline">
            读取刊物历史
          </Link>
        </main>
      </>
    );
  return (
    <>
      <PublicationNavigation />
      <PublicEditionReader edition={edition} navigation={navigation} />
    </>
  );
}
