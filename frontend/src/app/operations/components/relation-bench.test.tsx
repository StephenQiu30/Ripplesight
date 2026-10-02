// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  normalizeRelationGold,
  normalizeRelationPredictions,
  RelationBench,
} from "./relation-bench";
const api = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  run: vi.fn(),
  import: vi.fn(),
}));
vi.mock("@/api/yunyingweihu", () => ({
  listOperatorSelectBench: api.list,
  getOperatorRelationBench: api.get,
  runOperatorRelationBench: api.run,
  importOperatorRelationBench: api.import,
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const gold = [
  {
    case_id: "release",
    a: { title: "Acme release", source: "Acme", first_party: true },
    b: { title: "Acme adoption", source: "Lab" },
    gold_relation: "SAME_STORY",
  },
];
it("preserves same-story progress and explicit unknown result rather than fabricating unrelated", () => {
  expect(normalizeRelationGold(JSON.stringify(gold))[0].gold_relation).toBe(
    "SAME_STORY",
  );
  const values = normalizeRelationPredictions({
    model: [
      {
        case_id: "release",
        relation: null,
        confidence: null,
        error_code: "ai_outcome_unknown",
      },
    ],
  });
  expect(values.model[0].error_code).toBe("ai_outcome_unknown");
  expect(values.model[0].relation).toBeNull();
  expect(() =>
    normalizeRelationPredictions({
      model: [{ case_id: "release", relation: "SAME_STORY", confidence: null }],
    }),
  ).toThrow();
  expect(() =>
    normalizeRelationGold(
      JSON.stringify([{ ...gold[0], gold_relation: "UNK" }]),
    ),
  ).toThrow();
});
it("keeps failed admission identity for explicit replay and never auto-runs from reading", async () => {
  api.list.mockResolvedValue([]);
  api.run.mockRejectedValue(new Error("disabled"));
  render(<RelationBench token="session-only" />);
  fireEvent.change(screen.getByLabelText("关系评测名称"), {
    target: { value: "Controlled" },
  });
  fireEvent.change(screen.getByLabelText("关系评测原因"), {
    target: { value: "固定样本" },
  });
  fireEvent.change(screen.getByLabelText("关系评测模型"), {
    target: { value: "controlled" },
  });
  const file = new File([JSON.stringify(gold)], "gold.json", {
    type: "application/json",
  });
  Object.defineProperty(file, "text", {
    value: async () => JSON.stringify(gold),
  });
  fireEvent.change(screen.getByLabelText(/关系样本 JSON/), {
    target: { files: [file] },
  });
  expect(api.run).not.toHaveBeenCalled();
  fireEvent.submit(
    screen.getByRole("button", { name: "排队关系评测" }).closest("form")!,
  );
  await waitFor(() => expect(api.run).toHaveBeenCalledTimes(1));
  await screen.findByText(/输入已保留/);
  fireEvent.submit(
    screen.getByRole("button", { name: "排队关系评测" }).closest("form")!,
  );
  await waitFor(() => expect(api.run).toHaveBeenCalledTimes(2));
  expect(api.run.mock.calls[0][0].operation_id).toEqual(
    api.run.mock.calls[1][0].operation_id,
  );
  expect(api.run.mock.calls[1][1].headers["X-HotKey-Operator-Token"]).toBe(
    "session-only",
  );
});
