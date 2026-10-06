import { PageState } from "@/components/system/page-state";

export default function Loading() {
  return (
    <PageState
      state="loading"
      eyebrow="报告阅读"
      title="正在读取报告内容"
      description="正在读取正文、目录与往期刊物。"
      loadingLayout="detail"
    />
  );
}
