import { PageHeader } from "@/components/system/page-header";
import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { FeedbackForm } from "@/app/feedback/components/feedback-form";
export const metadata: Metadata = {
  title: "反馈",
  robots: { index: false, follow: false },
};
export default async function FeedbackPage() {
  await connection();
  return (
    <>
      <UI.Content>
        <PageHeader
          breadcrumbs={[{ label: "事件", href: "/events" }, { label: "反馈" }]}
          title={<>反馈</>}
          description={<>描述使用中遇到的问题。截图仅供运营人员查看。</>}
        />
        <FeedbackForm />
      </UI.Content>
    </>
  );
}
