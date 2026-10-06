import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/api/xitongzhuangtai", () => ({ getReadiness: vi.fn() }));

import { BasicLayout } from "@/layout/basic-layout";
import { Progress } from "@/components/ui/progress";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

// 生产环境 CSP 的 style-src 只放行 nonce 与哈希，服务端渲染出的 style 属性会被浏览器丢弃。
// 外壳与基础组件的样式必须来自类名，不能依赖 style 属性。下列三项来自 next/image 与
// Radix，被拦截也不影响布局，因此单独放行。
const harmlessThirdPartyStyles = new Set([
  "color:transparent",
  "outline:none",
  "position:relative",
]);
describe("server-rendered markup has no inline style attributes", () => {
  it.each([
    ["anonymous shell", null],
    [
      "signed-in shell",
      {
        user: {
          id: "00000000-0000-4000-8000-000000000002",
          username: "reader",
          has_password: true,
          github_connected: false,
          email: null,
        },
        expires_at: "2100-01-01T00:00:00Z",
      } satisfies HotKeyAPI.IdentitySessionView,
    ],
  ])("%s", (_, session) => {
    const html = renderToString(
      <BasicLayout session={session}>
        <Progress value={40} />
        <ToggleGroup type="single" spacing={0} aria-label="筛选">
          <ToggleGroupItem value="a">甲</ToggleGroupItem>
        </ToggleGroup>
      </BasicLayout>,
    );
    const styles = [...html.matchAll(/\sstyle="([^"]*)"/g)].map(
      (match) => match[1],
    );
    expect(
      styles.filter((style) => !harmlessThirdPartyStyles.has(style)),
    ).toEqual([]);
  });
});
