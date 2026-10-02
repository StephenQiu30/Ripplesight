import type { Metadata } from "next";
import { connection } from "next/server";
import Link from "next/link";
import { FeedbackForm } from "@/app/feedback/components/feedback-form";
import { BrandLockup } from "@/components/brand/brand-lockup";
export const metadata: Metadata = {
  title: "反馈",
  robots: { index: false, follow: false },
};
export default async function FeedbackPage() {
  await connection();
  return (
    <>
      <header className="mx-auto flex min-h-20 max-w-3xl items-center justify-between px-5">
        <BrandLockup href="/" compactOnMobile />
        <Link href="/events">返回事件</Link>
      </header>
      <main className="mx-auto max-w-3xl px-5 py-12">
        <h1 className="text-3xl font-semibold">反馈</h1>
        <p className="text-muted-foreground mt-3">
          描述使用中遇到的问题。截图仅供运营人员查看。
        </p>
        <FeedbackForm />
      </main>
    </>
  );
}
