import type { MetadataRoute } from "next";

import {
  SYSTEM_PAGE_PREFIXES,
  PUBLIC_READING_PREFIXES,
} from "@/components/auth/access";
import { getSiteOrigin } from "@/components/site/welcome-metadata";

export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/", ...PUBLIC_READING_PREFIXES],
      disallow: ["/login", "/api/", ...SYSTEM_PAGE_PREFIXES],
    },
    sitemap: `${getSiteOrigin()}/sitemap.xml`,
  };
}
