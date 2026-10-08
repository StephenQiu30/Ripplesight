import { Content, Heading } from "@/components/ui/content";
import { Skeleton } from "@/components/ui/skeleton";

export function HomeLoading() {
  return (
    <Content
      layout="stack"
      className="min-w-0 gap-8"
      role="status"
      aria-label="首页加载中"
      aria-busy="true"
    >
      <Heading level={1} className="sr-only">
        正在读取首页资讯
      </Heading>
      <Content aria-hidden="true" layout="stack" className="gap-3">
        <Skeleton className="h-10 w-48 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-64 motion-reduce:animate-none" />
      </Content>
      <Content
        aria-hidden="true"
        className="grid grid-cols-2 gap-6 border-y py-5 md:grid-cols-4"
      >
        {[0, 1, 2, 3].map((i) => (
          <Content key={i} layout="stack" className="gap-3">
            <Skeleton className="h-3 w-24 motion-reduce:animate-none" />
            <Skeleton className="h-8 w-16 motion-reduce:animate-none" />
          </Content>
        ))}
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
        <Content layout="stack" className="hidden md:flex">
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
