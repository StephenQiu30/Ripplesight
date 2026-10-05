// @vitest-environment happy-dom
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/react";
import { createRef, StrictMode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { EditorConfig, OutputData } from "@editorjs/editorjs";

const runtime = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock("@/components/editor/tools", () => ({
  loadEditor: runtime.load,
  editorI18n: {},
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
import { Editor, type EditorHandle, textToDocument } from "@/components/editor";

class Instance {
  static all: Instance[] = [];
  data: OutputData;
  isReady = Promise.resolve();
  destroy = vi.fn();
  render = vi.fn(async (data: OutputData) => {
    this.data = data;
  });
  save = vi.fn(async () => this.data);
  constructor(public config: EditorConfig) {
    this.data = config.data!;
    Instance.all.push(this);
  }
}
function readyRuntime() {
  runtime.load.mockResolvedValue({ EditorJS: Instance, tools: {} });
}
afterEach(() => {
  cleanup();
  Instance.all = [];
  vi.resetAllMocks();
});

it("keeps one instance under StrictMode and destroys it exactly once on unmount", async () => {
  readyRuntime();
  const view = render(
    <StrictMode>
      <Editor value={textToDocument("内容")} aria-label="正文" />
    </StrictMode>,
  );
  await waitFor(() => expect(Instance.all).toHaveLength(1));
  await waitFor(() =>
    expect(
      screen.getByRole("group", { name: "正文" }).getAttribute("aria-busy"),
    ).toBe("false"),
  );
  view.unmount();
  await waitFor(() => expect(Instance.all[0].destroy).toHaveBeenCalledOnce());
});

it("waits for queued external renders before save and sanitizes external data", async () => {
  readyRuntime();
  const ref = createRef<EditorHandle>();
  const view = render(<Editor ref={ref} value={textToDocument("第一版")} />);
  await waitFor(() => expect(Instance.all).toHaveLength(1));
  await act(async () => {
    await ref.current!.save();
  });
  view.rerender(
    <Editor
      ref={ref}
      value={{
        blocks: [
          { type: "paragraph", data: { text: '<b onclick="bad()">新版</b>' } },
        ],
      }}
    />,
  );
  let saved: OutputData | undefined;
  await act(async () => {
    saved = await ref.current!.save();
  });
  expect(saved?.blocks[0].data.text).toBe("<b>新版</b>");
});

it("does not re-render onChange echoes or publish stale async saves", async () => {
  readyRuntime();
  const onChange = vi.fn();
  const initial = textToDocument("第一版");
  const view = render(<Editor value={initial} onChange={onChange} />);
  await waitFor(() => expect(Instance.all).toHaveLength(1));
  await act(async () => {
    await Instance.all[0].isReady;
  });
  const instance = Instance.all[0];
  const current = { ...textToDocument("用户编辑"), time: 1, version: "2.31.7" };
  instance.data = current;
  await act(async () => {
    await instance.config.onChange?.({} as never, {} as never);
  });
  expect(onChange).toHaveBeenCalledWith(current);
  view.rerender(<Editor value={current} onChange={onChange} />);
  expect(instance.render).not.toHaveBeenCalled();

  let resolveOld!: (value: OutputData) => void;
  instance.save.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
  );
  let pending: unknown;
  act(() => {
    pending = instance.config.onChange?.({} as never, {} as never);
  });
  view.rerender(
    <Editor value={textToDocument("切换文档")} onChange={onChange} />,
  );
  await act(async () => {
    resolveOld(textToDocument("旧响应"));
    await pending;
  });
  expect(onChange).toHaveBeenCalledTimes(1);
});

it("reports initialization failure and can retry without a leftover instance", async () => {
  runtime.load.mockRejectedValueOnce(new Error("chunk failed"));
  const onError = vi.fn();
  render(<Editor value={textToDocument("内容")} onError={onError} />);
  await screen.findByText("编辑器暂时不可用。");
  expect(onError).toHaveBeenCalledOnce();
  readyRuntime();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  await waitFor(() => expect(Instance.all).toHaveLength(1));
  await waitFor(() =>
    expect(screen.queryByText("编辑器暂时不可用。")).toBeNull(),
  );
});

it("does not construct or notify after unmount while lazy chunks are pending", async () => {
  let finish!: (value: unknown) => void;
  runtime.load.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const onReady = vi.fn();
  const view = render(
    <Editor value={textToDocument("内容")} onReady={onReady} />,
  );
  view.unmount();
  await act(async () => {
    finish({ EditorJS: Instance, tools: {} });
  });
  expect(Instance.all).toHaveLength(0);
  expect(onReady).not.toHaveBeenCalled();
});

it("captures content mutations before the core's debounced callback", async () => {
  readyRuntime();
  const onChange = vi.fn();
  render(<Editor value={textToDocument("旧内容")} onChange={onChange} />);
  await waitFor(() => expect(Instance.all).toHaveLength(1));
  await waitFor(() =>
    expect(screen.queryByLabelText("正在加载编辑器")).toBeNull(),
  );
  const instance = Instance.all[0];
  const content = document.createElement("div");
  content.className = "ce-block__content";
  (instance.config.holder as HTMLElement).append(content);
  await act(async () => {
    instance.data = textToDocument("立即输入");
    content.textContent = "立即输入";
  });
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(textToDocument("立即输入")),
  );
  // The delayed core callback must not publish a duplicate snapshot.
  await act(async () => {
    await instance.config.onChange?.({} as never, {} as never);
  });
  expect(onChange).toHaveBeenCalledOnce();
});
