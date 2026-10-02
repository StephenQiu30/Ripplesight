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
      <div>
        <Link href="/events" className="mb-8 inline-block text-sm">
          返回事件
        </Link>
        <h1 className="text-3xl font-semibold">反馈</h1>
        <p className="text-muted-foreground mt-3">
          描述使用中遇到的问题。截图仅供运营人员查看。
        </p>
        <FeedbackForm />
      </div>
    </>
  );
}
