import Link from "next/link";

import { EditionPrint } from "@/components/publication/edition-print";
import { PosterDownload } from "@/components/publication/poster-download";
import {
  PublicItemCards,
  publicationTime,
} from "@/components/publication/reading-parts";

const labels = { daily: "日报", weekly: "周报", monthly: "月报" } as const;

export function PublicEditionReader({
  edition,
  navigation,
}: {
  edition: HotKeyAPI.PublicEditionView;
  navigation?: HotKeyAPI.PublicEditionNavigationView;
}) {
  const references = (ids: string[]) =>
    edition.entries.filter((entry) => ids.includes(entry.id));
  return (
    <div className="space-y-9">
      <div className="text-muted-foreground flex flex-wrap gap-4 text-sm">
        <span>
          {labels[edition.kind]} · {edition.key}
        </span>
        <span>修订 {edition.revision}</span>
        <time dateTime={edition.created_at}>
          {publicationTime(edition.created_at)}
        </time>
      </div>
      <h1 className="text-3xl leading-tight font-medium">{edition.title}</h1>
      <p className="text-muted-foreground leading-8 whitespace-pre-wrap">
        {edition.lead}
      </p>
      <div className="text-muted-foreground flex flex-wrap gap-4 text-sm">
        <span>
          {edition.metrics.selected_count ?? edition.entries.length} 条精选
        </span>
        <span>{edition.metrics.sources_count ?? 0} 个来源</span>
        <a
          href={`/reports/${edition.kind}/${encodeURIComponent(edition.key)}.md`}
          className="underline"
        >
          读取 Markdown
        </a>
        <Link href={`/feed/${edition.kind}.xml`} className="underline">
          订阅{labels[edition.kind]}
        </Link>
      </div>
      {edition.highlights.length ? (
        <section>
          <h2 className="text-xl font-medium">重点关注</h2>
          <PublicItemCards items={references(edition.highlights)} />
        </section>
      ) : null}
      {edition.themes.map((theme) => (
        <section key={theme.heading} className="space-y-4">
          <h2 className="text-xl font-medium">{theme.heading}</h2>
          <p className="text-muted-foreground leading-7 whitespace-pre-wrap">
            {theme.summary}
          </p>
          <PublicItemCards items={references(theme.content_ids)} />
        </section>
      ))}
      {edition.sections.map((section) => (
        <section key={section.label}>
          <h2 className="text-xl font-medium">{section.label}</h2>
          <PublicItemCards items={references(section.content_ids)} />
        </section>
      ))}
      {edition.flashes.length ? (
        <section>
          <h2 className="text-xl font-medium">更多动态</h2>
          <PublicItemCards items={references(edition.flashes)} />
        </section>
      ) : null}
      <details className="space-y-4">
        <summary className="cursor-pointer text-sm">
          全部 {edition.entries.length} 条固定引用
        </summary>
        <PublicItemCards items={edition.entries} />
      </details>
      <nav
        aria-label="刊期导航"
        className="flex flex-wrap gap-5 text-sm print:hidden"
      >
        {navigation?.previous ? (
          <Link href={navigation.previous.reading_url} className="underline">
            ← 上一期 · {navigation.previous.key}
          </Link>
        ) : null}
        <Link href={`/reports/${edition.kind}/archive`} className="underline">
          全部{labels[edition.kind]}历史
        </Link>
        <Link href={`/reports/${edition.kind}`} className="underline">
          最新{labels[edition.kind]}
        </Link>
        {navigation?.next ? (
          <Link href={navigation.next.reading_url} className="underline">
            下一期 · {navigation.next.key} →
          </Link>
        ) : null}
      </nav>
      <div className="flex flex-wrap items-start gap-4 print:hidden">
        <EditionPrint />
        <PosterDownload target={{ kind: edition.kind, key: edition.key }} />
      </div>
    </div>
  );
}
