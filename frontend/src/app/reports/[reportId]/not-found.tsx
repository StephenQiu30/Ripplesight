import { PageState } from "@/components/system/page-state";

export default function NotFound() {
  return (
    <PageState
      state="empty"
      eyebrow="刊物阅读"
      title="这份刊物目前不可公开阅读"
      description="刊物不存在、已撤回或许可已经变化。请返回首页查看其他公开内容。"
    />
  );
}
