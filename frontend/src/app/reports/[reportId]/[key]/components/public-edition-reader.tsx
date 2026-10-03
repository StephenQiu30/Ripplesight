import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
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
    <div className="flex flex-col gap-y-9">
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
        <section key={theme.heading} className="flex flex-col gap-y-4">
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
      <Collapsible className="flex flex-col gap-4">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
          >
            <span className="min-w-0 text-left">
              全部 {edition.entries.length} 条固定引用
            </span>
            <ChevronDownIcon
              aria-hidden="true"
              data-icon="inline-end"
              className="group-data-[state=open]:rotate-180"
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent forceMount className="data-[state=closed]:hidden">
          <PublicItemCards items={edition.entries} />
        </CollapsibleContent>
      </Collapsible>
      <NavigationMenu
        viewport={false}
        className="max-w-full justify-start print:hidden"
        aria-label="刊期导航"
      >
        <NavigationMenuList className="flex-wrap justify-start gap-2">
          {navigation?.previous ? (
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href={navigation.previous.reading_url}>
                  ← 上一期 · {navigation.previous.key}
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ) : null}
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href={`/reports/${edition.kind}/archive`}>
                全部{labels[edition.kind]}历史
              </Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href={`/reports/${edition.kind}`}>
                最新{labels[edition.kind]}
              </Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          {navigation?.next ? (
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <Link href={navigation.next.reading_url}>
                  下一期 · {navigation.next.key} →
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ) : null}
        </NavigationMenuList>
      </NavigationMenu>
      <div className="flex flex-wrap items-start gap-4 print:hidden">
        <EditionPrint />
        <PosterDownload target={{ kind: edition.kind, key: edition.key }} />
      </div>
    </div>
  );
}
