import { connection } from "next/server";

import { InformationPage } from "@/components/site/information-page";
import { ContactPanel } from "./components/contact-panel";
import { welcomeMetadata } from "@/components/site/welcome-metadata";

export const metadata = welcomeMetadata(
  "/contact",
  "联系",
  "查看知微见澜维护者的公开联系入口，登录后提交站内反馈。",
);
export default async function ContactPage() {
  await connection();
  return (
    <InformationPage title="联系">
      <ContactPanel />
    </InformationPage>
  );
}
