import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import Link from "next/link";
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
        <Link href="/events" className="mb-8 inline-block text-sm">
          返回事件
        </Link>
        <UI.Heading level={1} className="text-3xl font-semibold">
          反馈
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-3">
          描述使用中遇到的问题。截图仅供运营人员查看。
        </UI.Text>
        <FeedbackForm />
      </UI.Content>
    </>
  );
}
