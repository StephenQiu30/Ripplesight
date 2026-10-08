import * as UI from "@/components/ui/content";
import { PageState } from "@/components/system/page-state";

export default function Loading() {
  return (
    <>
      <UI.Heading level={1} className="sr-only">
        页面加载中…
      </UI.Heading>
      <PageState
        state="loading"
        title="页面加载中"
        description="正在读取页面内容。"
      />
    </>
  );
}
