import type { MetadataRoute } from "next";

import {
  PUBLIC_PAGE_PATHS,
  PUBLIC_READING_PREFIXES,
} from "@/components/auth/access";
import { getSiteOrigin } from "@/components/site/welcome-metadata";

export const dynamic = "force-dynamic";

export default function sitemap(): MetadataRoute.Sitemap {
  const origin = getSiteOrigin();
  return [...PUBLIC_PAGE_PATHS, ...PUBLIC_READING_PREFIXES]
    .filter((path) => path !== "/login" && path !== "/items")
    .map((path) => ({
      url: new URL(path, `${origin}/`).href,
    }));
}
