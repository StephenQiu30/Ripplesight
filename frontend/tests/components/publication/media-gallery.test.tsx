// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MediaGallery } from "@/components/publication/media-gallery";
vi.mock("next/image", () => ({
  default: ({
    src,
    alt,
    onError,
    width,
    height,
    className,
  }: React.ComponentProps<"img">) => (
    // Browser media decoding is replaced only in this component test.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt ?? ""}
      onError={onError}
      width={width}
      height={height}
      className={className}
    />
  ),
}));
afterEach(cleanup);
const id = "00000000-0000-4000-8000-000000000001";
const media = (
  key: string,
  kind: "image" | "video",
  url: string,
): HotKeyAPI.PublicMediaView => ({
  key,
  kind,
  original_url: "https://source.example/asset",
  alt: key,
  reading_url: url,
  state: "available",
  width: 640,
  height: 480,
});
it("embeds only a permitted owned media URL, opens a keyboard gallery, and keeps unmirrored sources as links", async () => {
  const { container } = render(
    <MediaGallery
      media={[
        media("许可图片一", "image", `/api/publication/media/${id}/full/site`),
        media(
          "许可图片二",
          "image",
          `/api/publication/media/${id}/image-720/site`,
        ),
        media("外部图片", "image", "https://source.example/untrusted"),
        media(
          "许可视频",
          "video",
          `/api/publication/media/${id}/original/site`,
        ),
      ]}
    />,
  );
  expect(container.querySelectorAll('img[src^="https:"]')).toHaveLength(0);
  expect(container.querySelector("video")?.getAttribute("src")).toBe(
    `/api/publication/media/${id}/original/site`,
  );
  expect(container.querySelector("video")?.getAttribute("preload")).toBe(
    "metadata",
  );
  expect(screen.getByRole("link", { name: /外部图片/ })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "放大 许可图片一" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    screen.getByRole("link", { name: "读取原尺寸图片" }).getAttribute("href"),
  ).toBe(`/api/publication/media/${id}/full/site`);
  fireEvent.keyDown(dialog, { key: "ArrowRight" });
  expect(
    screen.getByRole("link", { name: "读取原尺寸图片" }).getAttribute("href"),
  ).toBe(`/api/publication/media/${id}/image-720/site`);
  expect(screen.getByText("2 / 2")).toBeTruthy();
});
it("does not render stale or path-escaping cached media", () => {
  const { container } = render(
    <MediaGallery
      media={[
        {
          ...media("已撤回", "image", `/api/publication/media/${id}/full/site`),
          state: "stale",
        },
        media(
          "路径越界",
          "image",
          `/api/publication/media/${id}/full/site?redirect=https://evil.example`,
        ),
      ]}
    />,
  );
  expect(container.querySelectorAll("img,video")).toHaveLength(0);
  expect(screen.queryByRole("button", { name: /放大/ })).toBeNull();
});
