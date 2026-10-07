import type { Metadata } from "next";

export function getSiteOrigin() {
  const configured =
    process.env.NEXT_PUBLIC_SITE_ORIGIN ??
    process.env.HOTKEY_WEB_ORIGIN ??
    "http://127.0.0.1:8666";
  const origin = new URL(configured);
  if (!/^https?:$/.test(origin.protocol) || origin.username || origin.password)
    throw new Error("公开站点地址必须使用 http 或 https 且不能包含凭据");
  return origin.origin;
}

export function welcomeMetadata(
  path: string,
  title: string,
  description: string,
): Metadata {
  const origin = getSiteOrigin();
  const canonical = new URL(path, `${origin}/`).href;
  return {
    title,
    description,
    metadataBase: new URL(origin),
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: {
      title,
      description,
      url: canonical,
      siteName: "Ripplesight",
      locale: "zh_CN",
      type: "website",
      images: [
        {
          url: "/brand/hero-brand-soft.png",
          width: 366,
          height: 366,
          alt: "Ripplesight",
        },
      ],
    },
    twitter: {
      card: "summary",
      title,
      description,
      images: ["/brand/hero-brand-soft.png"],
    },
  };
}
