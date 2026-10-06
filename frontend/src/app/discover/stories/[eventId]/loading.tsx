import * as UI from "@/components/ui/content";
import { PageState } from "@/components/system/page-state";

export default function Loading() {
  return (
    <>
      <UI.Heading level={1} className="sr-only">
        正在读取公开事件
      </UI.Heading>
      <PageState
        state="loading"
        eyebrow="公开事件"
        title="正在读取公开事件"
        description="正在读取摘要、公开事实和来源。"
        loadingLayout="detail"
      />
    </>
  );
}
