import type { Metadata } from "next";
import { connection } from "next/server";

import { InformationPage } from "@/components/site/information-page";
import { ContactPanel } from "./components/contact-panel";

export const metadata: Metadata = {
  title: "联系",
  robots: { index: false, follow: false },
};
export default async function ContactPage() {
  await connection();
  return (
    <InformationPage title="联系">
      <ContactPanel />
    </InformationPage>
  );
}
