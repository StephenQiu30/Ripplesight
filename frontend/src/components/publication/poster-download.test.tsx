// @vitest-environment happy-dom
import { Blob as NodeBlob } from "node:buffer";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PosterDownload } from "./poster-download";
const api = vi.hoisted(() => ({
  item: vi.fn(),
  story: vi.fn(),
  edition: vi.fn(),
}));
vi.mock("@/api/gongkaifenfa", () => ({
  getPublicationItemPosterPng: api.item,
  getPublicationStoryPosterPng: api.story,
  getPublicationEditionPosterPng: api.edition,
}));
vi.mock("next/image", () => ({
  default: ({ alt }: { alt: string }) => <span aria-label={alt} />,
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});
it("downloads guarded server PNG bytes and removes an old preview when a new request is withdrawn", async () => {
  vi.stubGlobal("Blob", NodeBlob);
  const create = vi
    .spyOn(URL, "createObjectURL")
    .mockReturnValue("blob:guarded-png");
  const revoke = vi
    .spyOn(URL, "revokeObjectURL")
    .mockImplementation(() => undefined);
  api.story
    .mockResolvedValueOnce(
      new NodeBlob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 1])], {
        type: "image/png",
      }),
    )
    .mockRejectedValueOnce(new Error("withdrawn"));
  render(<PosterDownload target={{ eventId: "fixed-story" }} />);
  fireEvent.click(screen.getByRole("button", { name: "生成海报 PNG" }));
  const link = await screen.findByRole("link", { name: "下载海报 PNG" });
  expect(link.getAttribute("href")).toBe("blob:guarded-png");
  expect(api.story).toHaveBeenCalledWith(
    { event_id: "fixed-story" },
    { responseType: "blob" },
  );
  expect(create).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "生成海报 PNG" }));
  await screen.findByText(/许可已变化/);
  expect(screen.queryByRole("link", { name: "下载海报 PNG" })).toBeNull();
  await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:guarded-png"));
});
it("rejects a typed error payload disguised as PNG without creating a downloadable object", async () => {
  vi.stubGlobal("Blob", NodeBlob);
  const create = vi.spyOn(URL, "createObjectURL");
  api.item.mockResolvedValue(
    new NodeBlob(['{"error":"withdrawn"}'], { type: "image/png" }),
  );
  render(<PosterDownload target={{ contentId: "fixed-item" }} />);
  fireEvent.click(screen.getByRole("button", { name: "生成海报 PNG" }));
  await screen.findByText(/当前不可读取/);
  expect(create).not.toHaveBeenCalled();
  expect(screen.queryByRole("link", { name: "下载海报 PNG" })).toBeNull();
});
