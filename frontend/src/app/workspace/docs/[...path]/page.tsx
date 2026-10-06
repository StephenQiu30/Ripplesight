import type { Metadata } from "next";
import { headers } from "next/headers";
import { connection } from "next/server";
import { compileMdx } from "nextra/compile";
import { evaluate } from "nextra/evaluate";
import {
  getWorkspaceDocument,
  listWorkspaceDocuments,
} from "@/api/xiangmuwendang";
import {
  DocumentArticle,
  documentComponents,
} from "@/components/ui/workspace-markdown";
import { decodeDocumentPath } from "@/components/editor/document-path";
import { documentRemark } from "@/components/editor/document-rendering";
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";
import { DocumentWorkspace } from "../components/document";
export const metadata: Metadata = {
  title: "项目文档",
  robots: { index: false, follow: false },
};
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ path: string[] }>;
  searchParams: Promise<{ snapshot?: string; history?: string }>;
}) {
  await connection();
  const segments = (await params).path;
  const query = await searchParams;
  let loaded;
  try {
    const path = decodeDocumentPath(segments);
    const doc = await getWorkspaceDocument({
      path,
      snapshot_id: query.snapshot,
      history: query.history === "true",
    });
    const catalog = await listWorkspaceDocuments({
      snapshot_id: doc.snapshot_id,
      history: query.history === "true",
    });
    const compiled = await compileMdx(doc.reading_markdown, {
      mdxOptions: {
        format: "md",
        remarkPlugins: [documentRemark(doc.sections)],
      },
      codeHighlight: false,
      isPageImport: false,
      search: false,
    });
    const { default: Content } = evaluate(
      compiled,
      documentComponents(doc.snapshot_id, query.history === "true"),
    );
    loaded = { doc, catalog, Content };
  } catch (error) {
    return (
      <PageState
        state={
          error instanceof ApiRequestError && error.status === 403
            ? "forbidden"
            : "error"
        }
        errorCode={error instanceof ApiRequestError ? error.code : undefined}
        httpStatus={error instanceof ApiRequestError ? error.status : undefined}
        eyebrow="项目文档"
        title={
          error instanceof ApiRequestError && error.status === 403
            ? "没有文档访问权限"
            : "无法读取文档"
        }
        description={
          error instanceof ApiRequestError
            ? error.message
            : "文档暂不可用，请返回目录重试。"
        }
      />
    );
  }
  const { doc, catalog, Content } = loaded;
  return (
    <DocumentWorkspace
      key={doc.snapshot_id + doc.path}
      doc={doc}
      catalog={catalog}
      nonce={(await headers()).get("x-nonce") ?? undefined}
    >
      <DocumentArticle>
        <Content />
      </DocumentArticle>
    </DocumentWorkspace>
  );
}
