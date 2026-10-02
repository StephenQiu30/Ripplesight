import type { MetadataRoute } from "next";

import { PUBLIC_PAGE_PATHS } from "@/components/auth/access";
import { getSiteOrigin } from "@/components/site/welcome-metadata";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  const origin = getSiteOrigin();
  return PUBLIC_PAGE_PATHS.filter((path) => path !== "/login").map((path) => ({
    url: new URL(path, `${origin}/`).href,
  }));
}
