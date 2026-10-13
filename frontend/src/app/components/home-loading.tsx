import { PageHeader } from "@/components/system/page-header";
import { Content } from "@/components/ui/content";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadingSignal } from "@/components/system/global-loading";

export function HomeLoading() {
  return (
    <Content
      layout="stack"
      className="min-w-0 gap-6 md:gap-8"
      role="status"
      aria-label="首页加载中"
      aria-busy="true"
    >
      <LoadingSignal />
      <Content layout="stack" className="gap-1">
        <PageHeader
          titleAppearance="home"
          title={<>今日 AI 热点</>}
          description={<>正在加载公开事件与日报…</>}
        />
      </Content>
      <Content
        aria-hidden="true"
        className="grid grid-cols-2 gap-4 border-y py-4 md:gap-6 md:py-5 @min-[40rem]/page:grid-cols-4"
      >
        {[0, 1, 2, 3].map((i) => (
          <Content key={i} layout="stack" className="gap-3">
            <Skeleton className="h-3 w-24 motion-reduce:animate-none" />
            <Skeleton className="h-8 w-16 motion-reduce:animate-none" />
          </Content>
        ))}
      </Content>
      <Content aria-hidden="true" className="@min-[56rem]/page:hidden">
        <Skeleton className="h-18 w-full rounded-xl motion-reduce:animate-none" />
      </Content>
      <Content aria-hidden="true" className="reading-columns">
        <Content layout="stack" className="min-w-0 gap-0">
          <Content className="border-b pb-4">
            <Skeleton className="h-9 w-3/4 motion-reduce:animate-none" />
          </Content>
          {[0, 1, 2].map((i) => (
            <Content key={i} layout="stack" className="gap-4 border-b py-6">
              <Skeleton className="h-3 w-28 motion-reduce:animate-none" />
              <Skeleton className="h-6 w-5/6 motion-reduce:animate-none" />
              <Skeleton className="hidden h-12 w-full motion-reduce:animate-none md:block" />
              <Skeleton className="h-3 w-1/2 motion-reduce:animate-none" />
            </Content>
          ))}
        </Content>
        <Content layout="stack" className="hidden @min-[56rem]/page:flex">
          <Skeleton className="h-28 w-full motion-reduce:animate-none" />
          <Skeleton className="h-5 w-32 motion-reduce:animate-none" />
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton
              key={i}
              className="h-6 w-full motion-reduce:animate-none"
            />
          ))}
        </Content>
      </Content>
    </Content>
  );
}
