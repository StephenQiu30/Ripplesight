import * as UI from "@/components/ui/content";
import { Viewer } from "@/components/editor";
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
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { EditionPrint } from "@/components/publication/edition-print";
import { EditionCopyLink } from "@/components/publication/edition-copy-link";
import { PosterDownload } from "@/components/publication/poster-download";
import { publicationTime } from "@/components/publication/reading-format";
import { EditionFailure } from "../../components/edition-state";
import { EditionContent, EditionReferenceTable } from "./edition-content";
import { editionReadingSections } from "./edition-sections";
import styles from "./public-edition-reader.module.css";

const labels = { daily: "日报", weekly: "周报", monthly: "月报" } as const;

export function PublicEditionReader({
  edition,
  navigation,
  catalogue,
  catalogueError,
  navigationError,
}: {
  edition: HotKeyAPI.PublicEditionView;
  navigation?: HotKeyAPI.PublicEditionNavigationView;
  catalogue?: HotKeyAPI.PublicEditionCatalogueView;
  catalogueError?: unknown;
  navigationError?: unknown;
}) {
  const sections = editionReadingSections(edition);
  const outline = [
    ...sections.map(({ id, title }) => ({ id, title })),
    ...(edition.entries.length
      ? [{ id: "edition-references", title: "固定引用" }]
      : []),
  ];
  // Compare dates only within a kind; never replace the requested edition with a nearby one.
  const past =
    catalogue?.entries.filter((entry) => entry.key < edition.key) ?? [];
  const readingUrl = `/reports/${edition.kind}/${encodeURIComponent(edition.key)}`;
  const selectedCount = edition.metrics.selected_count;
  const sourcesCount = edition.metrics.sources_count;
  return (
    <UI.Content
      data-edition-reader=""
      className={`${styles.reader} grid min-w-0 grid-cols-1 items-start gap-10 lg:grid-cols-3 lg:gap-12 print:block`}
    >
      <UI.Content
        as="article"
        aria-label={edition.title}
        className="flex min-w-0 flex-col gap-10 lg:col-span-2"
      >
        <UI.Content as="header" className="flex flex-col gap-4">
          <UI.Text tone="muted" size="sm">
            <UI.InlineCode>
              {labels[edition.kind]} · {edition.key} · 修订 {edition.revision}
            </UI.InlineCode>
          </UI.Text>
          <UI.Heading level={1} className="break-words">
            {edition.title}
          </UI.Heading>
          <UI.Text tone="muted" size="xs">
            生成于{" "}
            <UI.Timestamp dateTime={edition.created_at}>
              <UI.InlineCode>
                {publicationTime(edition.created_at)}
              </UI.InlineCode>
            </UI.Timestamp>
          </UI.Text>
          <UI.Text tone="muted" size="xs">
            覆盖{" "}
            <UI.Timestamp dateTime={edition.window_start}>
              <UI.InlineCode>
                {publicationTime(edition.window_start)}
              </UI.InlineCode>
            </UI.Timestamp>{" "}
            至{" "}
            <UI.Timestamp dateTime={edition.window_end}>
              <UI.InlineCode>
                {publicationTime(edition.window_end)}
              </UI.InlineCode>
            </UI.Timestamp>
          </UI.Text>
          {edition.lead.trim() ? <Viewer value={edition.lead} /> : null}
          <Separator />
          <UI.Content className="flex flex-wrap gap-4">
            <UI.Text size="sm">
              <UI.InlineCode>
                {typeof selectedCount === "number" &&
                Number.isFinite(selectedCount)
                  ? selectedCount
                  : edition.entries.length}
              </UI.InlineCode>{" "}
              {typeof selectedCount === "number" &&
              Number.isFinite(selectedCount)
                ? "条精选"
                : "条固定引用"}
            </UI.Text>
            {typeof sourcesCount === "number" &&
            Number.isFinite(sourcesCount) ? (
              <UI.Text size="sm">
                <UI.InlineCode>{sourcesCount}</UI.InlineCode> 个来源
              </UI.Text>
            ) : null}
          </UI.Content>
          <Separator />
        </UI.Content>
        {sections.map((section) => (
          <EditionContent key={section.id} section={section} />
        ))}
        {edition.entries.length ? (
          <UI.Content
            as="section"
            aria-labelledby="edition-references"
            className="flex min-w-0 flex-col gap-4"
          >
            <UI.Heading
              level={2}
              id="edition-references"
              tabIndex={-1}
              className="scroll-mt-6"
            >
              固定引用
            </UI.Heading>
            <Collapsible className="flex flex-col gap-4">
              <CollapsibleTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full justify-between whitespace-normal print:hidden"
                >
                  全部 {edition.entries.length} 条固定引用
                  <ChevronDownIcon aria-hidden="true" data-icon="inline-end" />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent
                forceMount
                data-edition-references=""
                className="data-[state=closed]:hidden"
              >
                <EditionReferenceTable
                  items={edition.entries}
                  labelledBy="edition-references"
                />
              </CollapsibleContent>
            </Collapsible>
          </UI.Content>
        ) : !sections.length ? (
          <Empty>
            <EmptyHeader>
              <EmptyDescription>本期暂无可公开的条目。</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : null}
        <NavigationMenu
          viewport={false}
          className="max-w-full justify-start print:hidden"
          aria-label="刊期导航"
        >
          <NavigationMenuList className="flex-wrap justify-start gap-2">
            {navigation?.previous ? (
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <UI.TextLink href={navigation.previous.reading_url}>
                    ← 上一期 · {navigation.previous.key}
                  </UI.TextLink>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ) : null}
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <UI.TextLink href={`/reports/${edition.kind}/archive`}>
                  全部{labels[edition.kind]}历史
                </UI.TextLink>
              </NavigationMenuLink>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <NavigationMenuLink asChild>
                <UI.TextLink href={`/reports/${edition.kind}`}>
                  最新{labels[edition.kind]}
                </UI.TextLink>
              </NavigationMenuLink>
            </NavigationMenuItem>
            {navigation?.next ? (
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <UI.TextLink href={navigation.next.reading_url}>
                    下一期 · {navigation.next.key} →
                  </UI.TextLink>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ) : null}
          </NavigationMenuList>
        </NavigationMenu>
      </UI.Content>
      <UI.Content
        as="aside"
        aria-label={`${labels[edition.kind]}操作与往期`}
        data-edition-sidebar=""
        className="flex min-w-0 flex-col gap-8 print:hidden"
      >
        <UI.Content className="flex flex-col gap-3" aria-label="刊物操作">
          <Button asChild>
            <UI.TextLink href={`/feed/${edition.kind}.xml`}>
              订阅{labels[edition.kind]}
            </UI.TextLink>
          </Button>
          <UI.Content className="flex flex-wrap gap-2">
            <EditionCopyLink href={readingUrl} />
            <EditionPrint />
          </UI.Content>
          <Button asChild variant="outline">
            <UI.TextLink href={`${readingUrl}.md`}>读取 Markdown</UI.TextLink>
          </Button>
          <PosterDownload target={{ kind: edition.kind, key: edition.key }} />
        </UI.Content>
        {outline.length ? (
          <UI.Content className="flex flex-col gap-3">
            <UI.Heading level={2}>本期目录</UI.Heading>
            <NavigationMenu
              viewport={false}
              orientation="vertical"
              aria-label="本期目录"
              className="max-w-full items-start justify-start"
            >
              <NavigationMenuList className="flex-col items-stretch gap-1">
                {outline.map((heading) => (
                  <NavigationMenuItem key={heading.id}>
                    <NavigationMenuLink asChild>
                      <UI.TextLink
                        href={`#${heading.id}`}
                        className="break-words"
                      >
                        {heading.title}
                      </UI.TextLink>
                    </NavigationMenuLink>
                  </NavigationMenuItem>
                ))}
              </NavigationMenuList>
            </NavigationMenu>
          </UI.Content>
        ) : null}
        <UI.Content
          as="section"
          aria-label="往期刊物"
          className="flex flex-col gap-4"
        >
          <UI.Heading level={2}>往期{labels[edition.kind]}</UI.Heading>
          {catalogueError ? (
            <EditionFailure error={catalogueError} href={readingUrl} />
          ) : past.length ? (
            <ItemGroup className="gap-0">
              {past.map((entry) => (
                <Item key={entry.key} asChild className="px-0 py-4">
                  <UI.TextLink href={entry.reading_url}>
                    <ItemContent className="min-w-0 gap-2">
                      <UI.Text tone="muted" size="xs">
                        <UI.InlineCode>{entry.key}</UI.InlineCode>
                      </UI.Text>
                      <UI.Text size="sm" className="break-words">
                        {entry.title}
                      </UI.Text>
                    </ItemContent>
                  </UI.TextLink>
                </Item>
              ))}
            </ItemGroup>
          ) : (
            <UI.Text tone="muted" size="sm">
              暂无更早的公开刊物。
            </UI.Text>
          )}
          <Button asChild variant="ghost" className="justify-start">
            <UI.TextLink href={`/reports/${edition.kind}/archive`}>
              查看全部历史
            </UI.TextLink>
          </Button>
        </UI.Content>
        {navigationError ? (
          <EditionFailure error={navigationError} href={readingUrl} />
        ) : null}
      </UI.Content>
    </UI.Content>
  );
}
