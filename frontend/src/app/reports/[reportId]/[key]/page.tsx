import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import {
  getPublicEditionNavigation,
  listPublicEditionCatalogue,
} from "@/api/gongkaikanwumulu";
import { getPublicEdition } from "@/api/gongkaifabu";
import { EditionFailure } from "../components/edition-state";
import { ApiRequestError } from "@/request";
import { PublicEditionReader } from "./components/public-edition-reader";

type Parameters = { params: Promise<{ reportId: string; key: string }> };
function editionKind(value: string) {
  if (value !== "daily" && value !== "weekly" && value !== "monthly")
    notFound();
  return value;
}

export async function generateMetadata({
  params,
}: Parameters): Promise<Metadata> {
  const { reportId, key } = await params;
  try {
    const edition = await getPublicEdition({
      kind: editionKind(reportId),
      key,
    });
    return {
      title: edition.title,
      description: edition.lead,
      robots: { index: false, follow: false },
      alternates: { canonical: edition.canonical_url ?? undefined },
      openGraph: {
        title: edition.title,
        description: edition.lead,
        type: "article",
        images: edition.canonical_url
          ? [
              {
                url: new URL(
                  `/og/reports/${edition.kind}/${encodeURIComponent(edition.key)}.png`,
                  edition.canonical_url,
                ).href,
                width: 1200,
                height: 630,
              },
            ]
          : undefined,
      },
    };
  } catch {
    return { title: "刊期", robots: { index: false, follow: false } };
  }
}

export default async function PublicEditionPage({ params }: Parameters) {
  await connection();
  const { reportId: rawKind, key } = await params;
  const kind = editionKind(rawKind);
  let edition: HotKeyAPI.PublicEditionView;
  let navigation: HotKeyAPI.PublicEditionNavigationView | undefined;
  let catalogue: HotKeyAPI.PublicEditionCatalogueView | undefined;
  let catalogueError: unknown;
  let navigationError: unknown;
  try {
    const [content, neighbours, history] = await Promise.allSettled([
      getPublicEdition({ kind, key }),
      getPublicEditionNavigation({ kind, key }),
      listPublicEditionCatalogue({ kind, before_key: key, limit: 5 }),
    ]);
    if (content.status === "rejected") throw content.reason;
    edition = content.value;
    if (neighbours.status === "fulfilled") navigation = neighbours.value;
    else navigationError = neighbours.reason;
    if (history.status === "fulfilled") catalogue = history.value;
    else catalogueError = history.reason;
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    return (
      <>
        <EditionFailure
          error={error}
          href={`/reports/${kind}/${encodeURIComponent(key)}`}
        />
      </>
    );
  }
  return (
    <>
      <PublicEditionReader
        edition={edition}
        navigation={navigation}
        catalogue={catalogue}
        catalogueError={catalogueError}
        navigationError={navigationError}
      />
    </>
  );
}
