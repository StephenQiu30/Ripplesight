import { PageState } from "@/components/system/page-state";

export default function Loading() {
  return (
    <PageState
      state="loading"
      eyebrow="刊物历史"
      title="正在读取刊物历史"
      description="正在读取可公开刊期与日历。"
    />
  );
}
