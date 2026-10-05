// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import * as UI from "@/components/ui/content";
import { Input } from "@/components/ui/input";

afterEach(cleanup);

it("retains heading levels, article, definition list and inline text semantics", () => {
  const { container } = render(
    <UI.Content as="article" aria-label="资讯">
      <UI.Heading level={1}>标题</UI.Heading>
      <UI.Content as="dl">
        <UI.Content as="dt">来源</UI.Content>
        <UI.Content as="dd">
          <UI.Text as="span">RSS</UI.Text>
        </UI.Content>
      </UI.Content>
    </UI.Content>,
  );
  expect(screen.getByRole("heading", { level: 1 }).tagName).toBe("H1");
  expect(container.querySelector("article dl dt")?.textContent).toBe("来源");
  expect(container.querySelector("dd span")?.textContent).toBe("RSS");
});

it("retains native form validation, submit events and DOM refs", () => {
  const submit = vi.fn((event: React.FormEvent<HTMLFormElement>) =>
    event.preventDefault(),
  );
  let form: HTMLFormElement | null = null;
  render(
    <UI.Form
      ref={(node) => {
        form = node;
      }}
      aria-label="设置"
      onSubmit={submit}
    >
      <Input aria-label="名称" required />
    </UI.Form>,
  );
  expect(form!.checkValidity()).toBe(false);
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "reader" },
  });
  expect(form!.checkValidity()).toBe(true);
  fireEvent.submit(form!);
  expect(submit).toHaveBeenCalledTimes(1);
});

it("keeps document roots, download links and native media controls in static output", () => {
  const html = renderToStaticMarkup(
    <UI.DocumentRoot lang="zh-CN">
      <UI.DocumentBody>
        <UI.TextLink href="/download.md" download>
          下载
        </UI.TextLink>
        <UI.VideoPlayer controls src="/video.mp4" />
        <UI.AudioPlayer controls src="/audio.mp3" />
      </UI.DocumentBody>
    </UI.DocumentRoot>,
  );
  expect(html).toContain('<html lang="zh-CN">');
  expect(html).toContain("<body>");
  expect(html).toContain('download=""');
  expect(html).toContain(
    '<video data-slot="video-player" controls="" src="/video.mp4">',
  );
  expect(html).toContain(
    '<audio data-slot="audio-player" controls="" src="/audio.mp3">',
  );
});
