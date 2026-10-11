// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceSearchContract } from "@/components/monitors/source-search-contract";
import { TopicSettingsFields } from "@/components/monitors/topic-settings-fields";
import { Form } from "@/components/ui/content";
import { searchContract } from "./search-contract-fixture";

afterEach(cleanup);

describe("source query explanations", () => {
  it("opens all five conditions without submitting a form or changing sources", () => {
    const submit = vi.fn((event) => event.preventDefault());
    const change = vi.fn();
    render(
      <Form onSubmit={submit}>
        <TopicSettingsFields
          sourceOptions={[
            {
              sourceKey: "test",
              displayName: "样本来源",
              selectable: false,
              reason: "待验证",
              searchContract,
              connectionVersion: 4,
            },
          ]}
          sourceKeys={[]}
          onSourceKeysChange={change}
          disabled={false}
        />
      </Form>,
    );
    const toggle = screen.getByRole("button", {
      name: "样本来源查询范围与筛选",
    });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.getAttribute("type")).toBe("button");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("当前连接 v4")).toBeTruthy();
    expect(screen.getAllByRole("term")).toHaveLength(5);
    expect(screen.getByText("任意命中 · 上游候选 + 本地精筛")).toBeTruthy();
    expect(screen.getByText("全部包含 · 仅本地精筛")).toBeTruthy();
    expect(screen.getByText("搜索窗口 · 当前路径不支持")).toBeTruthy();
    expect(screen.getByText("仅筛选返回的标题与摘要。")).toBeTruthy();
    expect(screen.getByText("候选不等于全平台覆盖。")).toBeTruthy();
    expect(submit).not.toHaveBeenCalled();
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it.each([undefined, null, { ...searchContract, version: "future.v2" }])(
    "keeps missing or unrecognized descriptions unknown",
    (contract) => {
      render(
        <SourceSearchContract
          sourceName="旧来源"
          contract={contract as HotKeyAPI.SourceSearchContractView | null}
          connectionVersion={2}
        />,
      );
      fireEvent.click(screen.getByRole("button"));
      expect(screen.getByText(/查询处理未知/)).toBeTruthy();
      expect(screen.queryByText(/当前连接 v2/)).toBeNull();
      expect(screen.queryByText(/上游候选 \+/)).toBeNull();
    },
  );

  it.each([
    { basis: "preset", label: "预设路径说明，尚未配置" },
    { basis: "unconfigured", label: "尚未配置可识别的查询路径" },
    { basis: "connection", label: "当前连接；版本未知" },
  ] as const)(
    "distinguishes $basis from verified availability",
    ({ basis, label }) => {
      render(
        <SourceSearchContract
          sourceName="样本来源"
          contract={{ ...searchContract, basis }}
        />,
      );
      fireEvent.click(screen.getByRole("button"));
      expect(screen.getByText(label)).toBeTruthy();
      expect(
        screen.getByText(/准入、预算和采集完成以实际回执为准/),
      ).toBeTruthy();
    },
  );
});
