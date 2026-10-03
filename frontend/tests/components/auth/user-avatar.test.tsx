// @vitest-environment happy-dom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const read = vi.hoisted(() => vi.fn());
vi.mock("@/api/identity", () => ({ getIdentityAvatar: read }));
import { UserAvatar } from "@/components/auth/user-avatar";

const user: HotKeyAPI.IdentityUserView = {
  id: "owner",
  username: "reader",
  email: null,
  has_password: true,
  github_connected: false,
  avatar_sha256: "a".repeat(64),
};
beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("releases the previous blob and aborts pending reads when the avatar changes or unmounts", async () => {
  const create = vi
    .spyOn(URL, "createObjectURL")
    .mockReturnValue("blob:avatar");
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  read.mockResolvedValueOnce(new Blob(["image"], { type: "image/png" }));
  const view = render(<UserAvatar user={user} />);
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
  const firstSignal = read.mock.calls[0][1].signal as AbortSignal;
  read.mockReturnValueOnce(new Promise(() => {}));
  view.rerender(
    <UserAvatar user={{ ...user, avatar_sha256: "b".repeat(64) }} />,
  );
  expect(firstSignal.aborted).toBe(true);
  expect(revoke).toHaveBeenCalledWith("blob:avatar");
  const secondSignal = read.mock.calls[1][1].signal as AbortSignal;
  view.unmount();
  expect(secondSignal.aborted).toBe(true);
});

it("offers a retry after a failed read and does not accept a non-image response", async () => {
  read.mockResolvedValueOnce(new Blob(["error"], { type: "application/json" }));
  read.mockRejectedValueOnce(new Error("offline"));
  render(<UserAvatar user={user} retryable />);
  fireEvent.click(await screen.findByRole("button", { name: "重新加载头像" }));
  await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("头像暂不可用")).toBeTruthy();
});

it("ignores a response arriving after unmount without creating an object URL", async () => {
  const create = vi.spyOn(URL, "createObjectURL");
  let resolve: (body: Blob) => void = () => {};
  read.mockReturnValueOnce(
    new Promise<Blob>((done) => {
      resolve = done;
    }),
  );
  const view = render(<UserAvatar user={user} />);
  view.unmount();
  await act(async () => resolve(new Blob(["image"], { type: "image/png" })));
  expect(create).not.toHaveBeenCalled();
});
