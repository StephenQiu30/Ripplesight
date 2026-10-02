from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest

from leaderboard.fetch import (
    SOURCE_KEYS,
    FetchAccessDeniedError,
    LeaderboardFetchClient,
    epoch_configuration,
    parse_artificial_analysis,
    parse_epoch_archive,
    parse_livebench,
    parse_terminal_submission,
    parse_vals,
)


def replay_responses() -> dict[str, object]:
    import pyarrow as arrow
    import pyarrow.parquet as parquet

    responses: dict[str, object] = {
        "https://artificialanalysis.ai/api/v2/language/models/free?page=1": {
            "intelligence_index_version": 4.3,
            "pagination": {"has_more": False},
            "data": [
                {
                    "id": "aa",
                    "name": "GPT-5 (high)",
                    "slug": "gpt-5-high",
                    "release_date": None,
                    "evaluations": {"artificial_analysis_intelligence_index": 42},
                    "model_creator": {"name": "OpenAI"},
                }
            ],
        },
        "https://huggingface.co/api/datasets/lmarena-ai/leaderboard-dataset": {"sha": "a" * 40},
        "https://livebench.ai/": '<script src="/static/js/main.abc.js"></script>',
        "https://livebench.ai/static/js/main.abc.js": '["2026-01-01","2026-06-01","2026-09-30"]',
        "https://livebench.ai/categories_2026_09_30.json": {
            "Coding": ["c"],
            "Agentic Coding": ["a"],
            "Reasoning": ["r"],
            "Mathematics": ["m"],
            "Language": ["l"],
            "IF": ["i"],
        },
        "https://livebench.ai/table_2026_09_30.csv": "model,c,a,r,m,l,i\ngpt-5,60,40,30,50,70,90\n",
        ("https://api.github.com/repos/EQ-bench/EQ-bench-site/commits?per_page=1"): [
            {"sha": "b" * 40, "commit": {"committer": {"date": "2026-09-30T00:00:00Z"}}}
        ],
        "https://eqbench.com/creative_writing.js": (
            "const data=`model_name,elo_score\ngpt-5,1234\n`;"
        ),
        "https://eqbench.com/creative_writing_longform.js": (
            "const data=`model_name,overall_score_100\ngpt-5,70\n`;"
        ),
        "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json": {
            "generated_at": "2026-09-30T00:00:00Z",
            "n_tasks_in_set": 100,
            "rows": [
                {
                    "model": "gpt-5",
                    "harness": "mini-swe-agent",
                    "provider": "OpenAI",
                    "reasoning_effort": "high",
                    "config": "official",
                    "pass_rate": 0.8,
                    "ci_lo": 0.7,
                    "ci_hi": 0.9,
                    "n_attempted": 100,
                }
            ],
        },
        "https://maker.taptap.cn/leaderboard/data/latest.json": {"latest": "20260930"},
        "https://maker.taptap.cn/leaderboard/data/editions/20260930.json": {
            "edition": {
                "id": "20260930",
                "published_at": "2026-09-30",
                "dataset_version": "v2",
                "dataset_hash_prefix": "abc",
            },
            "main_board": [
                {
                    "model": "gpt-5@high",
                    "rank": 1,
                    "reasoning_effort": "high",
                    "provider": "OpenAI",
                    "l2": {"rate": 0.8, "ci95": [0.7, 0.9]},
                }
            ],
        },
        "https://www.mercor.com/blog/fixture": '{"datePublished":"2026-09-30"}',
    }
    arena_rows = [
        {
            "model_name": "gpt-5-high",
            "organization": "OpenAI",
            "license": "open",
            "rating": 1500.0,
            "rating_lower": 1490.0,
            "rating_upper": 1510.0,
            "vote_count": 1000,
            "rank": 1,
            "category": category,
            "leaderboard_publish_date": "2026-09-30",
        }
        for category in ("overall", "creative_writing")
    ]
    for config in ("text_style_control", "webdev", "vision_style_control"):
        buffer = io.BytesIO()
        parquet.write_table(arrow.Table.from_pylist(arena_rows), buffer)
        responses[
            "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/"
            f"{'a' * 40}/{config}/latest-00000-of-00001.parquet"
        ] = buffer.getvalue()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        for filename in (
            "frontiermath_tiers_1_3_v2.csv",
            "frontiermath_tier_4_v2.csv",
            "chess_puzzles.csv",
            "mystery_game_puzzles.csv",
            "simpleqa_verified.csv",
            "gpqa_diamond.csv",
            "mirrorcode.csv",
            "ebr_bench.csv",
        ):
            writer.writestr(
                filename,
                "Model version,mean_score,stderr,Started at\ngpt-5_high,0.7,0.1,2026-09-30\n",
            )
    responses["https://epoch.ai/data/benchmark_data.zip"] = archive.getvalue()
    benchmark = {
        "benchmarkId": "apex",
        "displayName": "APEX",
        "dataLink": "https://example.org/apex-v1",
        "blogLink": "https://www.mercor.com/blog/fixture",
        "globalLeaderboard": [
            {
                "model": {
                    "modelId": "gpt-5-high",
                    "effort": "high",
                    "releaseDate": None,
                    "provider": {"name": "OpenAI"},
                },
                "nSamples": 10,
                "passScores": [
                    {
                        "pass": "pass-1",
                        "harnessScores": [
                            {"harness": "loop_truncated_tools_agent", "score": 70, "error": 2}
                        ],
                    }
                ],
            }
        ],
    }
    responses["https://www.mercor.com/apex/apex-agents-leaderboard/"] = (
        '<script id="__NEXT_DATA__">'
        + json.dumps({"props": {"pageProps": {"benchmark": benchmark}}})
        + "</script>"
    )
    vals_data = {
        "metadata": [
            0,
            {
                "benchmark_id": [0, "FAB"],
                "version": [0, "v2"],
                "updated": [0, "2026-09-30"],
                "total_models": [0, 1],
            },
        ],
        "tasks": [
            0,
            {
                "overall": [
                    0,
                    {
                        "gpt-5": [
                            0,
                            {
                                "accuracy": [0, 70],
                                "stderr": [0, 2],
                                "reasoning_effort": [0, "high"],
                            },
                        ]
                    },
                ]
            },
        ],
    }
    props = json.dumps({"benchmarkView": [0, vals_data]}).replace('"', "&quot;")
    responses["https://www.vals.ai/benchmarks/fabv2"] = (
        '<astro-island component-url="BenchmarkView.js" props="' + props + '">'
    )
    repo = "https://api.github.com/repos/harbor-framework/terminal-bench"
    commit = [{"sha": "c" * 40, "commit": {"committer": {"date": "2026-09-30T00:00:00Z"}}}]
    responses[repo + "/commits?per_page=1"] = commit
    responses[repo + "/commits?per_page=1&path=leaderboard%2Fsubmissions"] = commit
    responses[repo + f"/contents/leaderboard/submissions?ref={'c' * 40}"] = [
        {"name": "fixture.json", "type": "file"}
    ]
    raw = f"https://raw.githubusercontent.com/harbor-framework/terminal-bench/{'c' * 40}/"
    responses[raw + "leaderboard/leaderboard.yaml"] = "name: 4-0-0\n"
    responses[raw + "leaderboard/src/leaderboard/core/hub.py"] = 'DATASET_REF = "main"\n'
    responses[raw + "leaderboard/src/leaderboard/ci/static_analysis.py"] = (
        "EXPECTED_TASK_COUNT = 100\n"
    )
    responses[raw + "leaderboard/submissions/fixture.json"] = {
        "source_filter": {"agent": "agent", "agent_version": "1", "model_name": "org/gpt-5"},
        "metadata": {
            "agent_display": {"label": "Agent"},
            "model_display": {"label": "GPT-5"},
            "model_org": {"label": "OpenAI"},
            "reasoning_effort": "high",
            "date": "2026-01-01",
        },
        "metrics": {"accuracy": 80, "accuracy_ci95_half_width": 5, "n_trials": 4},
    }
    return responses


@pytest.mark.parametrize("collector", list(SOURCE_KEYS))
def test_all_collectors_replay_full_official_response_shapes(collector: str) -> None:
    responses = replay_responses()
    authorized: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        value = responses.get(str(request.url))
        assert value is not None, f"Unexpected fixture URL {request.url}"
        if isinstance(value, bytes):
            return httpx.Response(200, content=value)
        if isinstance(value, str):
            return httpx.Response(200, text=value)
        return httpx.Response(200, json=value)

    def authorize(attempt: int) -> bool:
        authorized.append(attempt)
        return True

    client = LeaderboardFetchClient(
        allow_external_requests=True,
        before_request=authorize,
        api_key="fixture-only-key",
        transport=httpx.MockTransport(handle),
    )
    results = client.fetch(collector)
    assert tuple(result.source_key for result in results) == SOURCE_KEYS[collector]
    assert all(len(result.rows) == 1 for result in results)
    assert all(result.license and result.attribution_url for result in results)
    assert authorized == list(range(1, client.requests + 1))
    if collector == "arena":
        assert {result.metadata["datasetRevision"] for result in results} == {"a" * 40}
    if collector == "mercor":
        assert results[0].rows[0].raw_score == 70 and results[0].rows[0].lower_bound == 68
    if collector == "terminal-bench":
        assert results[0].rows[0].raw_score == 0.8 and results[0].rows[0].configuration.ineligible


def test_all_ten_fetchers_and_reference_boards_are_registered() -> None:
    assert len(SOURCE_KEYS) == 10
    assert "terminal-bench-4" in SOURCE_KEYS["terminal-bench"]
    assert "epoch-mirrorcode" in SOURCE_KEYS["epoch"]
    assert "livebench-general" in SOURCE_KEYS["livebench"]


def test_network_requires_explicit_scope_before_credential_or_transport_use() -> None:
    client = LeaderboardFetchClient()
    with pytest.raises(FetchAccessDeniedError):
        client.fetch("artificial-analysis")


def test_aa_uses_headline_only_not_price_or_latency() -> None:
    result = parse_artificial_analysis(
        [
            {
                "intelligence_index_version": 4.3,
                "data": [
                    {
                        "id": "id",
                        "name": "GPT-5 (high)",
                        "slug": "GPT-5",
                        "release_date": "2026-01-01",
                        "model_creator": {"name": "OpenAI"},
                        "pricing": {"price_1m_input_tokens": 10000},
                        "evaluations": {
                            "artificial_analysis_intelligence_index": 42,
                            "mmlu_pro": 0.99,
                        },
                    }
                ],
            }
        ]
    )
    assert len(result.rows) == 1 and result.rows[0].raw_score == 42
    assert result.rows[0].metric_key == "artificial-analysis:intelligence"
    assert result.metadata["intelligenceIndexVersion"] == 4.3
    assert "pricing" not in result.rows[0].metadata


def test_livebench_averages_complete_unrounded_task_categories_only() -> None:
    csv = "model,code1,code2,agent,reason,math,language,if\na,10,20,90,1,2,3,4\nb,10,,90,1,2,3,4\n"
    categories = {
        "Coding": ["code1", "code2"],
        "Agentic Coding": ["agent"],
        "Reasoning": ["reason"],
        "Mathematics": ["math"],
        "Language": ["language"],
        "IF": ["if"],
    }
    boards = parse_livebench("2026-09-30", categories, csv)
    coding = next(board for board in boards if board.source_key == "livebench-coding")
    assert [(row.base_name, row.raw_score) for row in coding.rows] == [("a", 52.5)]
    assert coding.rows[0].metadata["livebenchCategoryScore:Coding"] == 15.0


def test_epoch_requires_own_run_and_keeps_pre_release_as_excluded_reference() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        for filename in (
            "frontiermath_tiers_1_3_v2.csv",
            "frontiermath_tier_4_v2.csv",
            "chess_puzzles.csv",
            "mystery_game_puzzles.csv",
            "simpleqa_verified.csv",
            "gpqa_diamond.csv",
            "mirrorcode.csv",
            "ebr_bench.csv",
        ):
            writer.writestr(
                filename,
                "Model version,mean_score,stderr,Started at,Organization,Release date\n"
                "gpt-5_high,0.7,0.1,2026-09-30,OpenAI,2026-01-01\nthird-party,0.99,0.01,,,\n",
            )
    boards = parse_epoch_archive(archive.getvalue())
    assert len(boards) == 8
    assert boards[0].rows[0].raw_score == 0.7 and len(boards[0].rows) == 1
    assert boards[0].rows[0].lower_bound == pytest.approx(0.6)
    assert epoch_configuration("gpt-5_pre-release_high")[1].ineligible
    assert epoch_configuration("llama_8B")[0] == "llama_8B"


def test_vals_astro_serialized_props_and_standard_error() -> None:
    raw = {
        "metadata": [
            0,
            {
                "benchmark_id": [0, "FAB"],
                "version": [0, "v2"],
                "updated": [0, "2026-09-30"],
                "total_models": [0, 1],
            },
        ],
        "tasks": [
            0,
            {
                "overall": [
                    0,
                    {
                        "org/model": [
                            0,
                            {
                                "accuracy": [0, 70],
                                "stderr": [0, 2],
                                "reasoning_effort": [0, "high"],
                                "compute_effort": [0, None],
                                "provider": [0, "Org"],
                                "harness": [0, "fixed"],
                                "latency": [0, 1],
                                "cost_per_test": [0, 99],
                            },
                        ]
                    },
                ]
            },
        ],
    }
    props = json.dumps({"benchmarkView": [0, raw]}).replace('"', "&quot;")
    result = parse_vals('<astro-island component-url="BenchmarkView.js" props="' + props + '">')
    assert result.rows[0].raw_score == 70
    assert result.rows[0].lower_bound == 68 and result.rows[0].upper_bound == 72
    assert result.rows[0].configuration.rank == 500


def test_terminal_system_rows_never_vote_and_percent_to_fraction() -> None:
    submission = {
        "source_filter": {"agent": "a", "agent_version": "1", "model_name": "org/gpt-5"},
        "metadata": {
            "agent_display": {"label": "Agent"},
            "model_display": {"label": "GPT-5"},
            "model_org": {"label": "OpenAI"},
            "date": "2026-01-01",
            "reasoning_effort": "high",
        },
        "metrics": {"accuracy": 80, "accuracy_ci95_half_width": 5, "n_trials": 4},
    }
    row = parse_terminal_submission(
        "submission.json",
        submission,
        revision="abc",
        version="4.0.0",
        dataset_ref="main",
        task_count=100,
    )
    assert row.raw_score == 0.8 and row.lower_bound == 0.75
    assert row.configuration_key == "tb4:submission.json"
    assert row.configuration.ineligible and row.configuration.kind == "SCAFFOLDED"
    assert row.sample_size == 100


def test_every_redirect_request_has_its_own_durable_budget_receipt() -> None:
    authorized: list[int] = []
    settled: list[tuple[int, str]] = []

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/latest":
            return httpx.Response(302, headers={"location": "/2026-10-01"})
        return httpx.Response(200, json={"date": "2026-10-01", "rates": {"CNY": 7.0}})

    def reserve(index: int) -> bool:
        authorized.append(index)
        return True

    client = LeaderboardFetchClient(
        allow_external_requests=True,
        before_request=reserve,
        after_request=lambda index, outcome: settled.append((index, outcome)),
        transport=httpx.MockTransport(transport),
    )
    assert client.fetch_fx()["rates"]["CNY"] == 7.0
    assert authorized == [1, 2]
    assert settled == [(1, "succeeded"), (2, "succeeded")]
    assert client.requests == 2


def test_transport_unknown_is_settled_once_and_not_automatically_retried() -> None:
    settled: list[tuple[int, str]] = []

    def transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("fixture timeout", request=request)

    client = LeaderboardFetchClient(
        allow_external_requests=True,
        before_request=lambda _: True,
        after_request=lambda index, outcome: settled.append((index, outcome)),
        transport=httpx.MockTransport(transport),
    )
    with pytest.raises(httpx.ReadTimeout):
        client.fetch_fx()
    assert settled == [(1, "unknown")]
    assert client.requests == 1


def test_http_failure_still_consumes_and_settles_the_authorized_request() -> None:
    settled: list[tuple[int, str]] = []
    client = LeaderboardFetchClient(
        allow_external_requests=True,
        before_request=lambda _: True,
        after_request=lambda index, outcome: settled.append((index, outcome)),
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    with pytest.raises(RuntimeError, match="HTTP 503"):
        client.fetch_fx()
    assert settled == [(1, "failed")]
    assert client.requests == 1


def test_cancellation_after_reservation_releases_without_calling_transport() -> None:
    cancelled = False
    settled: list[tuple[int, str]] = []
    sent: list[httpx.Request] = []

    def reserve(_: int) -> bool:
        nonlocal cancelled
        cancelled = True
        return True

    def transport(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    client = LeaderboardFetchClient(
        allow_external_requests=True,
        before_request=reserve,
        after_request=lambda index, outcome: settled.append((index, outcome)),
        cancelled=lambda: cancelled,
        transport=httpx.MockTransport(transport),
    )
    with pytest.raises(FetchAccessDeniedError):
        client.fetch_fx()
    assert settled == [(1, "not_sent")]
    assert client.requests == 0 and not sent
