import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "AI Hotspot Radar",
  description: "Self-hosted AI hotspot monitoring MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
