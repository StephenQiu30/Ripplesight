import * as UI from "@/components/ui/content";
import { PageState } from "@/components/system/page-state";

export default function Loading() {
  return (
    <>
      <UI.Heading level={1} className="sr-only">
        正在读取报告内容
      </UI.Heading>
      <PageState
        state="loading"
        eyebrow="报告阅读"
        title="正在读取报告内容"
        description="正在读取正文、目录与往期刊物。"
        loadingLayout="detail"
      />
    </>
  );
}
