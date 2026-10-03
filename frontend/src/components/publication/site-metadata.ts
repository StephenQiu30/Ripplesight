import type { Metadata } from "next";
import { getPublicSiteMeta } from "@/api/zhandiziliao";

export function publicPageMetadata(
  site: HotKeyAPI.PublicSiteMetaView,
  options: {
    title: string;
    description?: string;
    path: string;
    imagePath?: string;
    indexable?: boolean;
  },
): Metadata {
  const canonical = new URL(options.path, `${site.public_base_url}/`).href;
  return {
    title: options.title,
    description: options.description,
    robots: {
      index: site.robots_index && options.indexable === true,
      follow: true,
    },
    alternates: { canonical },
    openGraph: {
      title: options.title,
      description: options.description,
      url: canonical,
      type: "website",
      images: options.imagePath
        ? [
            {
              url: new URL(options.imagePath, canonical).href,
              width: 1200,
              height: 630,
            },
          ]
        : undefined,
    },
  };
}
export async function publicSiteMetadata(
  options: Parameters<typeof publicPageMetadata>[1],
): Promise<Metadata> {
  try {
    return publicPageMetadata(await getPublicSiteMeta(), options);
  } catch {
    return {
      title: options.title,
      description: options.description,
      robots: { index: false, follow: false },
    };
  }
}
