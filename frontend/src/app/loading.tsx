import * as UI from "@/components/ui/content";
import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <UI.Content
      className="w-full"
      role="status"
      aria-label="页面加载中"
      aria-busy="true"
    >
      <UI.Heading level={1} className="sr-only">
        页面加载中…
      </UI.Heading>
      <UI.Content
        className="mx-auto flex max-w-3xl flex-col items-center"
        aria-hidden="true"
      >
        <Skeleton className="h-5 w-40 rounded-full" />
        <Skeleton className="mt-8 h-14 w-full max-w-2xl rounded-xl" />
        <Skeleton className="mt-4 h-7 w-full max-w-xl rounded-lg" />
      </UI.Content>
      <UI.Content
        className="mt-16 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:gap-6"
        aria-hidden="true"
      >
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} className="h-64 rounded-xl" />
        ))}
      </UI.Content>
    </UI.Content>
  );
}
