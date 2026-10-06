import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import * as UI from "@/components/ui/content";
import { ApiRequestError } from "@/request";

export function EditionFailure({
  error,
  href,
  headingLevel = 1,
}: {
  error: unknown;
  href: string;
  headingLevel?: 1 | 2;
}) {
  const known = error instanceof ApiRequestError ? error : null;
  const forbidden = known?.status === 401 || known?.status === 403;
  return (
    <PageState
      headingLevel={headingLevel}
      state={forbidden ? "forbidden" : "error"}
      eyebrow="公开刊物"
      title={
        forbidden
          ? "这份刊物目前不可公开阅读"
          : known?.code === "publication_not_configured"
            ? "公开刊物尚未发布"
            : known?.status === 404
              ? "这份刊物目前不可公开阅读"
              : "暂时无法读取刊物"
      }
      description={
        forbidden
          ? "公开刊物无需登录。请稍后重新读取，或返回首页查看其他公开内容。"
          : known?.status === 404
            ? "刊物不存在、已撤回或许可已经变化。"
            : "请重新读取；读取不会触发来源请求或模型调用。"
      }
      errorCode={known?.code ?? "publication_read_failed"}
      httpStatus={known?.status}
      action={
        <UI.Content className="flex flex-wrap items-center gap-3">
          <Button asChild variant="outline">
            <UI.TextLink href={href}>重新读取</UI.TextLink>
          </Button>
          {forbidden ? (
            <UI.InlineCode>
              {known?.code ?? "publication_read_failed"} · {known?.status}
            </UI.InlineCode>
          ) : null}
        </UI.Content>
      }
    />
  );
}
