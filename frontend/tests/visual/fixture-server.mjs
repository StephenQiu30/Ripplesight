// Local visual verification only. Never connect this fixture server to a deployment.
// Run from frontend: node tests/visual/fixture-server.mjs [port=8670]
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import { richFixtures } from "./rich-fixtures.mjs";
// Reuse existing typed contract samples without adding a second TS runner.
const fixtureRequire = createRequire(import.meta.url);
fixtureRequire.extensions[".ts"] = (module, filename) => {
  module._compile(
    ts.transpileModule(readFileSync(filename, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    filename,
  );
};
const {
  publicItem: baseItem,
  publicStory,
  reportSentiment,
  negativeSurge,
  heatHistory,
} = fixtureRequire("../app/components/home-fixtures.ts");
const fixtureId = "00000000-0000-4000-8000-000000000001";
const publicItem = {
  ...baseItem,
  id: fixtureId,
  reading_url: `/items/${fixtureId}`,
};
const { edition, editionEntry } = fixtureRequire(
  "../app/reports/edition-fixtures.ts",
);
const { board } = fixtureRequire("../components/leaderboard/fixtures.ts");
const session = {
  user: {
    id: "visual-user",
    username: "视觉测试",
    email: null,
    has_password: true,
    github_connected: false,
  },
  expires_at: "2099-01-01T00:00:00Z",
};
const topic = {
  id: "visual-topic",
  name: "视觉测试主题",
  status: "active",
  readiness_status: "ready",
  current_version: 2,
  rules: { match_any: ["人工智能", "大模型"], match_all: [], exclude: [] },
  source_keys: [],
  collection_interval_seconds: 3600,
  report_time: "08:00:00",
  report_timezone: "Asia/Shanghai",
  weekly_report_enabled: true,
  notification_target_names: [],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T01:00:00Z",
};
const emptyPage = { items: [], next_cursor: null };
const rich = richFixtures({ publicItem, publicStory, edition, board, topic });
let state = "normal";
let dataset = "minimal";
let surgeState = "triggered";
let historyState = "normal";
function historyFixture() {
  const value = structuredClone(heatHistory);
  if (historyState !== "normal") {
    const reason =
      historyState === "unavailable"
        ? "provenance_unknown"
        : historyState === "recomputed"
          ? "recomputed"
          : historyState === "source_changed"
            ? "source_changed"
            : "missing";
    value.trend = {
      state:
        historyState === "unavailable" ? "unavailable" : "insufficient_data",
      reason,
    };
    if (historyState === "source_changed")
      value.points.at(-1).segment_key = "changed-cohort";
    else {
      value.points.at(-1).value = null;
      value.points.at(-1).reason = reason;
    }
  }
  return value;
}

function surgeFixture(empty) {
  const value = structuredClone(negativeSurge);
  value.state = empty ? "empty" : surgeState;
  if (empty) {
    value.total_events = value.evaluated_events = value.triggered_count = 0;
    value.events = [];
    return value;
  }
  const event = value.events[0];
  event.state = surgeState;
  value.triggered_count = Number(surgeState === "triggered");
  value.not_triggered_count = Number(surgeState === "not_triggered");
  value.evaluated_events = value.triggered_count + value.not_triggered_count;
  value.insufficient_count = Number(surgeState === "insufficient_data");
  value.unavailable_count = Number(surgeState === "unavailable");
  value.not_configured_count = Number(surgeState === "not_configured");
  event.reasons = {
    triggered: [],
    not_triggered: ["ratio_increase_below_threshold"],
    insufficient_data: ["previous_empty", "previous_samples_insufficient"],
    unavailable: ["evidence_conflict"],
    not_configured: ["rule_not_configured", "previous_empty"],
  }[surgeState];
  if (surgeState === "not_configured") value.rule = null;
  if (!["triggered", "not_triggered"].includes(surgeState)) {
    event.ratio_increase = event.negative_count_increase = null;
  }
  if (["not_configured", "insufficient_data"].includes(surgeState)) {
    event.previous = {
      ...event.previous,
      sample_count: 0,
      valid_count: 0,
      negative: 0,
      positive: 0,
      neutral: 0,
      negative_ratio: null,
      analysis_coverage: null,
      source_keys: [],
    };
  }
  if (surgeState === "not_triggered") {
    event.current = {
      ...event.current,
      positive: 4,
      neutral: 4,
      negative: 2,
      negative_ratio: 0.2,
    };
    event.ratio_increase = event.negative_count_increase = 0;
    event.reasons = [
      "negative_count_below_threshold",
      "count_increase_below_threshold",
      "ratio_increase_below_threshold",
      "source_ratio_increase_below_threshold",
    ];
  }
  return value;
}
const error = (code) => ({
  code,
  message: "隔离视觉测试状态",
  request_id: "00000000-0000-4000-8000-000000000001",
});
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const path = url.pathname;
  const send = (body, status = 200) => {
    res.writeHead(status, {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    res.end(JSON.stringify(body));
  };
  if (path === "/__fixture/state") {
    const next = url.searchParams.get("value");
    if (
      [
        "normal",
        "empty",
        "error",
        "forbidden",
        "unauthorized",
        "loading",
      ].includes(next)
    )
      state = next;
    const nextDataset = url.searchParams.get("dataset");
    if (["minimal", "rich"].includes(nextDataset)) dataset = nextDataset;
    const nextHistory = url.searchParams.get("history");
    if (
      [
        "normal",
        "missing",
        "recomputed",
        "source_changed",
        "unavailable",
      ].includes(nextHistory)
    )
      historyState = nextHistory;
    const nextSurge = url.searchParams.get("surge");
    if (
      [
        "triggered",
        "not_triggered",
        "insufficient_data",
        "unavailable",
        "not_configured",
      ].includes(nextSurge)
    )
      surgeState = nextSurge;
    return send({ state, dataset });
  }
  if (req.method !== "GET") return send(error("fixture_read_only"), 405);
  if (path === "/api/identity/session") return send(session);
  if (state === "unauthorized") return send(error("fixture_unauthorized"), 401);
  if (state === "loading")
    await new Promise((resolve) => setTimeout(resolve, 12000));
  if (state === "error" || state === "forbidden")
    return send(
      error(state === "error" ? "fixture_unavailable" : "fixture_forbidden"),
      state === "error" ? 503 : 403,
    );
  const empty = state === "empty";
  const full = dataset === "rich";
  const items = full ? rich.items : [publicItem];
  const stories = full
    ? rich.stories
    : [
        publicStory,
        {
          ...publicStory,
          id: "story-2",
          title: "固定样本：从来源与讨论追踪事件变化",
        },
      ];
  const topics = full ? rich.topics : [topic];
  const currentEdition = full ? rich.edition : edition;
  const snapshotAt = full ? "2026-10-12T12:00:00Z" : "2026-10-06T08:00:00Z";
  const timedStories = stories.map((story, index) => ({
    sentiment: {
      ...reportSentiment,
      samples: story.reports.map((report) => ({
        ...reportSentiment.samples[0],
        content_id: report.id,
      })),
    },
    ...story,
    history: historyFixture(),
    timing: {
      snapshot_at: snapshotAt,
      reference_at: story.first_seen_at,
      reference_basis: "published",
      identified_at: new Date(
        Date.parse(snapshotAt) - (index ? 3600000 : 259200000),
      ).toISOString(),
      latest_development_at: index
        ? null
        : new Date(Date.parse(snapshotAt) - 1800000).toISOString(),
      development_fact_ids: index ? [] : ["visual-fact-1"],
      activity: index ? "new" : "existing_updated",
      occurred_at: null,
    },
  }));
  const currentEditionEntry = {
    ...editionEntry(currentEdition.key),
    title: currentEdition.title,
    created_at: currentEdition.created_at,
  };
  if (path === "/api/identity/options")
    return send({ password: !empty, email: !empty, github: !empty });
  if (path === "/api/publication/hot")
    return send({
      stories: empty ? [] : stories,
      next_cursor: null,
    });
  if (path === "/api/publication/home")
    return send({
      snapshot_at: snapshotAt,
      window_start: new Date(Date.parse(snapshotAt) - 86400000).toISOString(),
      scope: "public_readable_events",
      ranking_basis: "heat_then_recent",
      negative_surge: surgeFixture(empty),
      overview: {
        total_events: empty ? 0 : 83,
        new_events_24h: empty ? 0 : 4,
        updated_events_24h: empty ? 0 : 2,
        covered_sources: empty ? 0 : 9,
        time_unknown_events: empty ? 0 : 1,
        platform_count: null,
        negative_surge_count: null,
      },
      stories: empty ? [] : timedStories,
      sentiment: empty
        ? {
            ...reportSentiment,
            time_unknown_count: 0,
            samples: [],
            current: {
              ...reportSentiment.current,
              sample_count: 0,
              valid_count: 0,
              positive: 0,
              neutral: 0,
              negative: 0,
              excluded_counts: {},
              source_keys: [],
              negative_ratio: null,
              analysis_coverage: null,
            },
            previous: {
              ...reportSentiment.previous,
              sample_count: 0,
              valid_count: 0,
              excluded_counts: {},
              source_keys: [],
              analysis_coverage: null,
            },
          }
        : { ...reportSentiment, samples: [] },
    });
  if (path === "/api/publication/items")
    return send({
      items: empty ? [] : items,
      snapshot_at: snapshotAt,
      next_cursor: null,
      source_status: [],
    });
  if (path === "/api/publication/topics")
    return send({ topics: [], refresh_at: null });
  if (path === "/api/publication/timeline")
    return send({
      filters: {},
      cards: empty ? [] : items.map((item) => ({ kind: "item", item })),
      snapshot_at: snapshotAt,
      refresh_at: null,
      next_cursor: null,
    });
  if (/\/api\/publication\/stories\/[^/]+$/.test(path))
    return empty
      ? send(error("not_found"), 404)
      : send(
          timedStories.find((story) => story.id === path.split("/").at(-1)) ??
            timedStories[0],
        );
  if (path.endsWith("/developments"))
    return send({
      event_id: path.split("/").at(-2),
      revision: "visual-rich-1",
      developments: empty || !full ? [] : rich.developments,
      next_cursor: null,
    });
  if (/\/api\/publication\/items\/[^/]+(?:\/site)?$/.test(path))
    return send({
      ...(items.find((item) => path.includes(item.id)) ?? items[0]),
      body: "固定测试正文",
      body_format: "text",
      visibility: "summary",
      site_visibility: "summary",
      indexable: false,
    });
  if (path === "/api/contents") return send(emptyPage);
  if (path === "/api/publication/catalogue/editions")
    return send({
      kind: "daily",
      entries: empty ? [] : [currentEditionEntry],
      next_before_key: null,
    });
  if (path.includes("/navigation/"))
    return send({
      current: empty ? null : currentEditionEntry,
      previous: null,
      next: null,
    });
  if (path.startsWith("/api/publication/editions/"))
    return empty ? send(error("not_found"), 404) : send(currentEdition);
  if (path.startsWith("/api/leaderboard/boards/"))
    return send({
      ...(full ? rich.board : board),
      entries: empty ? [] : full ? rich.board.entries : board.entries,
    });
  if (path === "/api/topics")
    return send({ items: empty ? [] : topics, next_cursor: null });
  if (path.endsWith("/editorial-sources")) return send([]);
  if (path.startsWith("/api/topics/"))
    return empty
      ? send(error("not_found"), 404)
      : send(
          topics.find((item) => item.id === path.split("/").at(-1)) ??
            topics[0],
        );
  if (path === "/api/source-capabilities") return send(emptyPage);
  if (path === "/api/alerts") return send([]);
  return send(error("fixture_not_configured"), 404);
});
server.listen(Number(process.argv[2] || 8670), "127.0.0.1", () =>
  console.log("Visual fixture API listening on loopback; fixed samples only."),
);
