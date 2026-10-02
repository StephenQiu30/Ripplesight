import type { Metadata } from "next";
import { connection } from "next/server";
import { SiteManager } from "./components/site-manager";

export const metadata: Metadata = {
  title: "站点联系设置",
  robots: { index: false, follow: false },
};
export default async function SiteManagerPage() {
  await connection();
  return <SiteManager />;
}
