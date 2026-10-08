import { Fragment } from "react";
import { Viewer } from "@/components/editor";
import {
  categories,
  publicationTime,
} from "@/components/publication/reading-format";
import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { EditionReadingSection } from "./edition-sections";

export function EditionContent({
  section,
}: {
  section: EditionReadingSection;
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby={section.id}
      className="flex min-w-0 flex-col gap-4"
    >
      <UI.Heading
        level={2}
        id={section.id}
        tabIndex={-1}
        className="scroll-mt-6 break-words"
      >
        {section.title}
      </UI.Heading>
      {section.summary?.trim() ? <Viewer value={section.summary} /> : null}
      {section.items.length ? (
        section.id === "edition-highlights" ? (
          <ItemGroup className="gap-0">
            {section.items.map((item, index) => (
              <Item
                key={item.id}
                className="flex-nowrap items-start gap-2 border-0 px-0 py-2"
              >
                <UI.Text size="sm" tone="muted">
                  <UI.InlineCode>{index + 1}.</UI.InlineCode>
                </UI.Text>
                <ItemContent>
                  <UI.Text size="sm">
                    {item.summary || item.title}{" "}
                    <UI.TextLink
                      href={item.reading_url}
                      aria-label={`要点来源 ${index + 1}`}
                    >
                      [{index + 1}]
                    </UI.TextLink>
                  </UI.Text>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        ) : section.presentation === "table" ? (
          <EditionReferenceTable
            items={section.items}
            labelledBy={section.id}
          />
        ) : (
          <EditionEventBlocks items={section.items} />
        )
      ) : null}
    </UI.Content>
  );
}

export function EditionReferenceTable({
  items,
  labelledBy,
}: {
  items: HotKeyAPI.PublicItemView[];
  labelledBy: string;
}) {
  return (
    <Table aria-labelledby={labelledBy} tabIndex={0} className="min-w-xl">
      <TableHeader>
        <TableRow>
          <TableHead scope="col" className="w-12">
            序号
          </TableHead>
          <TableHead scope="col">资讯</TableHead>
          <TableHead scope="col" className="w-28">
            来源
          </TableHead>
          <TableHead scope="col" className="w-40">
            时间
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item, index) => (
          <TableRow key={item.id}>
            <TableCell>
              <UI.InlineCode>{index + 1}</UI.InlineCode>
            </TableCell>
            <TableCell className="whitespace-normal">
              <UI.Content className="flex flex-col gap-2 break-words">
                <UI.TextLink href={item.reading_url}>{item.title}</UI.TextLink>
                {item.summary ? (
                  <UI.Text size="sm" tone="muted">
                    {item.summary_origin === "source" ? "来源摘要：" : ""}
                    {item.summary}
                  </UI.Text>
                ) : null}
                {item.original_url ? (
                  <UI.TextLink
                    href={item.original_url}
                    target="_blank"
                    rel="noreferrer"
                    className="print:hidden"
                  >
                    <UI.Text as="span" size="xs">
                      来源原文 ↗
                    </UI.Text>
                  </UI.TextLink>
                ) : null}
              </UI.Content>
            </TableCell>
            <TableCell className="break-words whitespace-normal">
              {item.source.name}
            </TableCell>
            <TableCell className="whitespace-normal">
              <UI.Text size="xs" tone="muted">
                {item.published_at ? "发布于" : "发现于"}
              </UI.Text>
              <UI.Timestamp dateTime={item.published_at ?? item.timeline_at}>
                <UI.InlineCode>
                  {publicationTime(item.published_at ?? item.timeline_at)}
                </UI.InlineCode>
              </UI.Timestamp>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function EditionEventBlocks({ items }: { items: HotKeyAPI.PublicItemView[] }) {
  return (
    <ItemGroup className="gap-0">
      {items.map((item) => {
        const category = categories.find(([key]) => key === item.category)?.[1];
        return (
          <Fragment key={item.id}>
            <Separator />
            <Item asChild className="px-0 py-6">
              <UI.Content as="article" aria-label={item.title}>
                <ItemContent className="min-w-0 gap-3">
                  <UI.Content className="flex flex-wrap items-center gap-2">
                    {category ? (
                      <Badge variant="secondary">{category}</Badge>
                    ) : null}
                    <UI.Text as="span" tone="muted" size="xs">
                      {item.source.name}
                    </UI.Text>
                    <UI.Text as="span" tone="muted" size="xs">
                      {item.published_at ? "发布于 " : "发现于 "}
                      <UI.Timestamp
                        dateTime={item.published_at ?? item.timeline_at}
                      >
                        <UI.InlineCode>
                          {publicationTime(
                            item.published_at ?? item.timeline_at,
                          )}
                        </UI.InlineCode>
                      </UI.Timestamp>
                    </UI.Text>
                  </UI.Content>
                  <UI.Heading level={3} className="break-words">
                    <UI.TextLink href={item.reading_url}>
                      {item.title}
                    </UI.TextLink>
                  </UI.Heading>
                  <UI.Content className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                    <UI.Content layout="stack" className="gap-2">
                      <UI.Heading level={4} appearance="sidebar">
                        发生了什么
                      </UI.Heading>
                      {item.summary ? (
                        <Viewer value={item.summary} format="text" />
                      ) : (
                        <UI.Text size="sm" tone="muted">
                          暂无摘要。
                        </UI.Text>
                      )}
                    </UI.Content>
                    <UI.Content layout="stack" className="gap-2">
                      <UI.Heading level={4} appearance="sidebar">
                        大家怎么看
                      </UI.Heading>
                      <UI.Text size="sm" tone="muted">
                        暂无本期公开评论与情感观测。
                      </UI.Text>
                    </UI.Content>
                  </UI.Content>
                  <UI.Content className="flex flex-wrap gap-4 print:hidden">
                    {item.original_url ? (
                      <UI.TextLink
                        href={item.original_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <UI.Text as="span" size="sm">
                          来源原文 ↗
                        </UI.Text>
                      </UI.TextLink>
                    ) : null}
                    {item.event_id ? (
                      <UI.TextLink
                        href={`/discover/stories/${encodeURIComponent(item.event_id)}`}
                      >
                        <UI.Text as="span" size="sm">
                          事件脉络
                        </UI.Text>
                      </UI.TextLink>
                    ) : null}
                  </UI.Content>
                </ItemContent>
              </UI.Content>
            </Item>
          </Fragment>
        );
      })}
    </ItemGroup>
  );
}
