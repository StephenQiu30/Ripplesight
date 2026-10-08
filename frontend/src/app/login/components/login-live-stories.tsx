import { getPublicHotStories } from "@/api/gongkaifabu";
import * as UI from "@/components/ui/content";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { eventTime } from "@/components/events/reading-model";
export async function LoginLiveStories() {
  const data = await getPublicHotStories({ limit: 3 }).catch(() => null);
  if (!data?.stories.length)
    return (
      <UI.Text tone="muted" size="sm">
        公开事件发布后，会在这里呈现最新进展。
      </UI.Text>
    );
  return (
    <ItemGroup className="gap-0">
      {data.stories.slice(0, 3).map((story) => (
        <Item
          key={story.id}
          role="listitem"
          className="flex-nowrap gap-4 rounded-none border-x-0 border-t border-b-0 px-0 py-3"
        >
          <UI.Text size="xs" tone="muted" className="shrink-0">
            <UI.Timestamp
              dateTime={story.first_seen_at}
              title={eventTime(story.first_seen_at)}
            >
              <UI.InlineCode>
                {new Intl.DateTimeFormat("zh-CN", {
                  timeZone: "Asia/Shanghai",
                  hour: "2-digit",
                  minute: "2-digit",
                  hour12: false,
                }).format(new Date(story.first_seen_at))}
              </UI.InlineCode>
            </UI.Timestamp>
          </UI.Text>
          <ItemContent className="min-w-0">
            <UI.TextLink href={`/discover/stories/${story.id}`}>
              <UI.Text as="span" size="sm">
                {story.title}
              </UI.Text>
            </UI.TextLink>
          </ItemContent>
        </Item>
      ))}
    </ItemGroup>
  );
}
