import Link from "next/link";
import { Content, Text } from "@/components/ui/content";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
export function BasicFooter() {
  return (
    <Content
      as="footer"
      role="contentinfo"
      className="flex min-h-16 flex-wrap items-center justify-between gap-4 px-4 py-3 md:px-8 print:hidden"
    >
      <Text tone="muted" size="xs">
        © {new Date().getFullYear()} 知微见澜 Ripplesight
      </Text>
      <NavigationMenu viewport={false} aria-label="站点信息">
        <NavigationMenuList className="flex-wrap gap-3">
          {[
            ["/about", "关于"],
            ["/privacy", "隐私"],
            ["/terms", "条款"],
            ["/changelog", "更新日志"],
          ].map(([href, label]) => (
            <NavigationMenuItem key={href}>
              <NavigationMenuLink asChild>
                <Link href={href}>{label}</Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ))}
        </NavigationMenuList>
      </NavigationMenu>
    </Content>
  );
}
