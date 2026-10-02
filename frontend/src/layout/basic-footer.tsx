import Link from "next/link";

import { LayoutContainer } from "./layout-container";

export function BasicFooter() {
  return (
    <footer className="layout-region bg-background shrink-0 overflow-hidden print:hidden">
      <LayoutContainer className="text-muted-foreground flex min-h-16 flex-wrap items-center justify-between gap-x-6 gap-y-2 py-3 text-xs">
        <p>知微见澜 · Ripplesight</p>
        <nav aria-label="站点信息" className="flex flex-wrap gap-x-4 gap-y-2">
          <Link className="hover:text-foreground" href="/about">
            关于
          </Link>
          <Link className="hover:text-foreground" href="/privacy">
            隐私
          </Link>
          <Link className="hover:text-foreground" href="/terms">
            使用条款
          </Link>
          <Link className="hover:text-foreground" href="/contact">
            联系
          </Link>
        </nav>
      </LayoutContainer>
    </footer>
  );
}
