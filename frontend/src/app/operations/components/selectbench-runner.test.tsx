import { expect, it } from "vitest";
import { normalizeGold } from "./selectbench-runner";
it("reads AIHOT gold JSONL without losing occurrence material or stratified split", () => {
  const row = {
    caseId: "release-1",
    material: {
      title: "Acme model",
      bodyOriginal: "Actual announcement material",
      bodyZh: null,
      publishedAt: "2026-09-01T09:00:00+08:00",
      sourceName: "Acme Blog",
    },
    sourceFacts: { sourceKind: "rss", sourceTier: "T1", firstParty: true },
    samplingContext: {
      benchmarkSplit: "development",
      samplingStratum: "release",
    },
    gold: { decision: "select" },
  };
  const cases = normalizeGold(
    JSON.stringify(row) +
      "\n" +
      JSON.stringify({ ...row, caseId: "release-2" }),
  );
  expect(cases).toHaveLength(2);
  expect(cases[0]).toMatchObject({
    case_id: "release-1",
    body: "Actual announcement material",
    gold: "select",
    tier: "T1",
    first_party: true,
    split: "development",
    stratum: "release",
  });
  expect(normalizeGold(JSON.stringify({ cases }, null, 2))).toEqual(cases);
  expect(() => normalizeGold("{}")).toThrow();
});
