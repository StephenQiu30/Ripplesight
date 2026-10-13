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
      className="flex min-h-16 flex-col items-start justify-between gap-x-5 gap-y-2 px-4 py-6 md:flex-row md:items-center md:px-8 print:hidden"
    >
      <Text tone="muted" size="xs">
        © {new Date().getFullYear()} 知微见澜 Ripplesight
      </Text>
      <NavigationMenu viewport={false} aria-label="站点信息">
        <NavigationMenuList className="flex-wrap gap-5">
          {[
            ["/about", "关于"],
            ["/privacy", "隐私"],
            ["/terms", "条款"],
            ["/changelog", "更新日志"],
          ].map(([href, label]) => (
            <NavigationMenuItem key={href}>
              <NavigationMenuLink asChild size="footer">
                <Link href={href}>{label}</Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ))}
        </NavigationMenuList>
      </NavigationMenu>
    </Content>
  );
}
