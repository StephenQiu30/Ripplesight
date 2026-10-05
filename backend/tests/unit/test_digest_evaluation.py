import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from analysis.evaluation_digest import evaluate_event_digests, parse_digest_evaluation_jsonl
from cli.commands import app
from events.digest_prompts import render_event_digest_prompt, serialize_event_digest_data

CASES = Path(__file__).resolve().parents[1] / "fixtures" / "story-digest-evaluation.jsonl"


def test_offline_comparison_uses_same_production_inputs_and_scores_controlled_outputs():
    cases = parse_digest_evaluation_jsonl(CASES.read_text("utf-8"))
    report = evaluate_event_digests(cases)
    assert report["model_calls"] == 0 and report["mode"] == "controlled_offline"
    assert report["sample_size"] == 2
    assert report["prompt_versions"]["old"] != report["prompt_versions"]["new"]
    for case, row in zip(cases, report["cases"], strict=True):
        data = serialize_event_digest_data(case.members, case.facts)
        assert row["input"] == json.loads(data)
        assert row["new"]["prompt"] == render_event_digest_prompt(data)
        assert row["old"]["prompt"] == render_event_digest_prompt(data, legacy=True)
        assert row["old"]["summary"] == case.old_summary
        assert row["new"]["summary"] == case.new_summary
    new, old = report["summary"]["new"], report["summary"]["old"]
    assert new["compliant_rate"] == 1 and new["bench"]["tp"] == 2
    assert old["first_sentence_compliant_rate"] == 0 and old["bench"]["fn"] == 2
    assert old["paragraphs_compliant_rate"] == 0.5
    assert old["length_compliant_rate"] == new["length_compliant_rate"] == 1


def test_offline_missing_responses_count_in_denominator_and_bench_errors():
    cases = parse_digest_evaluation_jsonl(CASES.read_text("utf-8"))
    cases[0].new_summary = None
    report = evaluate_event_digests(cases)
    assert report["summary"]["new"]["bench"]["errors"] == 1
    assert report["summary"]["new"]["length_compliant_rate"] == 0.5
    assert report["summary"]["new"]["compliant_rate"] == 0.5


def test_offline_jsonl_is_strict_and_reports_lines_and_duplicate_ids():
    row = parse_digest_evaluation_jsonl(CASES.read_text("utf-8"))[0].model_dump_json()
    assert len(parse_digest_evaluation_jsonl("// comment\n\n" + row)) == 1
    with pytest.raises(ValueError, match="line 2: duplicate"):
        parse_digest_evaluation_jsonl(row + "\n" + row)
    with pytest.raises(ValueError, match="line 1: invalid"):
        parse_digest_evaluation_jsonl(row[:-1] + ',"summary_claim":1}')
    with pytest.raises(ValueError, match="no cases"):
        parse_digest_evaluation_jsonl("// empty")


def test_offline_input_over_limit_fails_without_a_partial_report():
    cases = parse_digest_evaluation_jsonl(CASES.read_text("utf-8"))
    cases[1].facts = [{"evidence": "甲" * 64000}]
    with pytest.raises(ValueError, match="event_digest_input_too_large"):
        evaluate_event_digests(cases)


def test_offline_cli_does_not_load_settings_database_or_ai(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline evaluation must not load runtime resources")

    for name in ("get_settings", "create_db_engine"):
        monkeypatch.setattr("cli.commands." + name, forbidden)
    monkeypatch.setattr("ai.services.create_ai_client", forbidden)
    result = CliRunner().invoke(app, ["evaluate-event-digests", "--cases", str(CASES)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["model_calls"] == 0
