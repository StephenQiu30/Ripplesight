import { PageState } from "@/components/system/page-state";
import { Content } from "@/components/ui/content";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";

export function HomeLoading() {
  return (
    <Content
      className="px-5 py-6 sm:px-8"
      role="status"
      aria-label="首页加载中"
      aria-busy="true"
    >
      <Content aria-hidden="true" layout="stack" className="pb-6">
        <Skeleton className="h-8 w-48 motion-reduce:animate-none" />
        <Skeleton className="h-4 w-64 motion-reduce:animate-none" />
        <Separator />
        <Skeleton className="h-5 w-1/2 motion-reduce:animate-none" />
        <Separator />
      </Content>
      <Content className="grid gap-8 lg:grid-cols-3">
        <Content className="lg:col-span-2">
          <PageState
            state="loading"
            eyebrow="公开阅读"
            title="正在读取首页资讯"
            description="正在读取公开事件与资讯。"
          />
        </Content>
        <Content aria-hidden="true" layout="stack">
          <Skeleton className="h-5 w-32 motion-reduce:animate-none" />
          <Skeleton className="h-24 w-full motion-reduce:animate-none" />
          <Separator />
          <Skeleton className="h-5 w-32 motion-reduce:animate-none" />
          <Skeleton className="h-24 w-full motion-reduce:animate-none" />
        </Content>
      </Content>
    </Content>
  );
}
