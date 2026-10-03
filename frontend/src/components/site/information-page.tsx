import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import Link from "next/link";

export function InformationPage({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h1 className="text-3xl font-medium">{title}</h1>
      <div className="text-muted-foreground mt-8 flex flex-col gap-y-6 text-sm leading-7">
        {children}
      </div>
      <NavigationMenu
        viewport={false}
        className="mt-12 max-w-full justify-start"
        aria-label="站点说明"
      >
        <NavigationMenuList className="flex-wrap justify-start gap-2">
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/about">关于</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/changelog">变更记录</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/privacy">隐私与本机数据</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/terms">使用与内容许可</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/contact">联系</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/feedback">反馈</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
    </div>
  );
}
