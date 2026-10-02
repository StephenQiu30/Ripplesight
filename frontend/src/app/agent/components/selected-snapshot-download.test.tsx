// @vitest-environment happy-dom
import { Blob as NodeBlob } from "node:buffer";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SelectedSnapshotDownload } from "./selected-snapshot-download";

const api = vi.hoisted(() => ({ snapshot: vi.fn() }));

vi.mock("@/api/gongkaifabu", () => ({
  getSelectedPublicationSnapshot: api.snapshot,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

describe("selected snapshot download", () => {
  it("reads one generated snapshot on demand and downloads its epoch and cursor", async () => {
    vi.stubGlobal("Blob", NodeBlob);
    const snapshot: HotKeyAPI.SelectedSnapshotView = {
      epoch: "publication-epoch",
      sequence: 12,
      items: [],
      next_cursor: "next-page-cursor",
    };
    let resolve!: (value: HotKeyAPI.SelectedSnapshotView) => void;
    api.snapshot.mockReturnValue(
      new Promise<HotKeyAPI.SelectedSnapshotView>((done) => {
        resolve = done;
      }),
    );
    const create = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:selected-snapshot");
    const revoke = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => undefined);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(this.href).toBe("blob:selected-snapshot");
        expect(this.download).toBe("hotkey-selected-snapshot.json");
      });

    render(<SelectedSnapshotDownload />);
    expect(api.snapshot).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "精选同步快照" }));
    expect(api.snapshot).toHaveBeenCalledExactlyOnceWith({});
    expect(
      screen
        .getByRole("button", { name: "正在读取快照…" })
        .hasAttribute("disabled"),
    ).toBe(true);
    resolve(snapshot);

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    const blob = create.mock.calls[0][0] as NodeBlob;
    expect(blob.type).toBe("application/json");
    expect(JSON.parse(await blob.text())).toEqual(snapshot);
    expect(api.snapshot).toHaveBeenCalledTimes(1);
    expect(
      document.querySelector('a[download="hotkey-selected-snapshot.json"]'),
    ).toBeNull();
    await waitFor(() =>
      expect(revoke).toHaveBeenCalledExactlyOnceWith("blob:selected-snapshot"),
    );
  });

  it("shows a retryable failure without producing a download", async () => {
    const create = vi.spyOn(URL, "createObjectURL");
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    api.snapshot
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce({
        epoch: "retry-epoch",
        sequence: 0,
        items: [],
        next_cursor: null,
      } satisfies HotKeyAPI.SelectedSnapshotView);

    render(<SelectedSnapshotDownload />);
    fireEvent.click(screen.getByRole("button", { name: "精选同步快照" }));
    await screen.findByText("快照暂时无法下载，请重新尝试。");
    expect(create).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
    expect(
      screen
        .getByRole("button", { name: "精选同步快照" })
        .hasAttribute("disabled"),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "精选同步快照" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(api.snapshot).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("快照暂时无法下载，请重新尝试。")).toBeNull();
  });

  it("does not create a download after its page has unmounted", async () => {
    let resolve!: (value: HotKeyAPI.SelectedSnapshotView) => void;
    api.snapshot.mockReturnValue(
      new Promise<HotKeyAPI.SelectedSnapshotView>((done) => {
        resolve = done;
      }),
    );
    const create = vi.spyOn(URL, "createObjectURL");
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const { unmount } = render(<SelectedSnapshotDownload />);
    fireEvent.click(screen.getByRole("button", { name: "精选同步快照" }));
    unmount();
    resolve({ epoch: "late-epoch", sequence: 0, items: [], next_cursor: null });

    await waitFor(() => expect(api.snapshot).toHaveResolved());
    expect(create).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
  });
});
