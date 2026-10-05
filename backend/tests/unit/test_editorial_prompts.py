from pathlib import Path

import pytest

from analysis import prompts


def test_migrated_group_rules_include_occurrences_developments_and_roundups() -> None:
    rendered = prompts.render_editorial_prompt("group-pair")
    assert "SAME_OCCURRENCE" in rendered
    assert "SAME_STORY" in rendered
    assert "ROUNDUP" in rendered
    assert "{{>" not in rendered
    assert "具体发布对象或具体发生" in rendered
    assert "两个各自独立的产品更新" in rendered
    assert "多个演讲者的会议综述" in rendered
    assert "不能只抽取两篇共同提到的一个产品" in rendered


def test_editorial_prompt_uses_hotkey_brand_and_requires_all_inputs() -> None:
    assert "HotKey" in prompts.render_editorial_prompt("prefilter")
    with pytest.raises(ValueError, match="missing prompt value"):
        prompts.render_editorial_prompt("report-period")
    rendered = prompts.render_editorial_prompt(
        "report-period",
        {
            "kindName": "月报",
            "span": "个月",
            "sentences": "三句话",
            "chars": "200",
            "sections": "sections 留空。",
            "sectionsExample": "{}",
        },
    )
    assert "月报" in rendered
    assert "{{" not in rendered


def test_included_rule_change_changes_receipt_prompt_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "_EDITORIAL_PROMPT_DIR", tmp_path)
    (tmp_path / "entry.md").write_text("{{> rule}} {{siteName}}")
    (tmp_path / "rule.md").write_text("original rule")
    first = prompts.editorial_prompt_version("entry")
    assert prompts.render_editorial_prompt("entry") == "original rule HotKey"
    (tmp_path / "rule.md").write_text("revised rule")
    assert prompts.editorial_prompt_version("entry") != first
    assert prompts.render_editorial_prompt("entry") == "revised rule HotKey"


def test_prompt_values_are_data_and_are_not_recursively_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "_EDITORIAL_PROMPT_DIR", tmp_path)
    (tmp_path / "entry.md").write_text("Material: {{body}}")
    assert prompts.render_editorial_prompt("entry", {"body": "{{> secret}}"}) == (
        "Material: {{> secret}}"
    )


@pytest.mark.parametrize("name", ["../secret", "/tmp/secret", "name.md", "a/b", ""])
def test_editorial_prompt_name_cannot_escape_templates(name: str) -> None:
    with pytest.raises(ValueError, match="invalid prompt name"):
        prompts.render_editorial_prompt(name)


def test_missing_include_and_include_cycle_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "_EDITORIAL_PROMPT_DIR", tmp_path)
    (tmp_path / "entry.md").write_text("{{> missing}}")
    with pytest.raises(ValueError, match="missing prompt template"):
        prompts.render_editorial_prompt("entry")
    (tmp_path / "entry.md").write_text("{{> other}}")
    (tmp_path / "other.md").write_text("{{> entry}}")
    with pytest.raises(ValueError, match="prompt include cycle"):
        prompts.editorial_prompt_version("entry")


def test_all_migrated_templates_render_with_the_declared_values() -> None:
    values = {
        "facts": "已验证事实",
        "kindName": "月报",
        "span": "个月",
        "sentences": "三句话",
        "chars": "200",
        "sections": "sections 留空。",
        "sectionsExample": "{}",
        "columns": "模型",
        "categoryCount": "2",
        "categoryGuide": "模型与研究",
        "categoryTags": "model,research",
        "entities": "OpenAI",
        "entityTags": "openai",
        "topicTags": "ai",
        "body": "source body",
        "identity": "固定原文身份",
        "publishedDate": "2026-10-02",
        "sourceName": "测试来源",
        "title": "测试标题",
        "today": "2026-10-02",
        "quotedLabel": "引用来源",
        "quotedText": "quoted source",
        "post": "source post",
    }
    names = sorted(p.stem for p in prompts._EDITORIAL_PROMPT_DIR.glob("*.md"))
    assert len(names) == 26
    assert "group-batch" not in names and "group-signal" not in names
    for name in names:
        assert "{{" not in prompts.render_editorial_prompt(name, values)
        assert prompts.editorial_prompt_version(name).startswith(f"{name}@")
