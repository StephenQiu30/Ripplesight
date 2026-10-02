from analysis.editorial_translation import (
    assemble_translation,
    plan_translation,
    shield,
    unshield,
)


def test_media_code_links_are_shielded_and_restored_with_original_attributes() -> None:
    original = (
        '<a href="https://example.com/a?q=1">Read</a> <code>x &lt; 1</code>'
        '<img src="https://example.com/i.png" alt="image">'
    )
    protected = shield(original)
    assert "href=" not in protected.html and "src=" not in protected.html
    assert "x &lt; 1" not in protected.html
    answer = protected.html.replace("Read", "阅读")
    restored = unshield(answer, protected)
    assert restored and '<a href="https://example.com/a?q=1">阅读</a>' in restored
    assert "<code>x &lt; 1</code>" in restored and 'alt="image"' in restored


def test_missing_repeated_unknown_tokens_links_or_new_active_html_are_rejected() -> None:
    protected = shield('<a href="https://example.com">Read</a><code>value</code>')
    bad = [
        protected.html.replace("\u27e60\u27e7", ""),
        protected.html + "\u27e60\u27e7",
        protected.html + "\u27e61\u27e7",
        protected.html.replace('id="L0"', 'id="L1"'),
        protected.html + '<a id="L0">again</a>',
        protected.html + "<script>alert(1)</script>",
        protected.html + '<img src="https://example.com/new">',
        protected.html.replace('id="L0"', 'id="L0" href="https://evil.example"'),
    ]
    assert all(unshield(answer, protected) is None for answer in bad)


def test_leaf_segments_skip_code_preserve_structure_and_mark_missing_block_partial() -> None:
    plan = plan_translation(
        "<h2>Heading</h2><ul><li>First <code>code</code></li></ul>"
        "<pre>Do not translate code</pre><p>Last</p>"
    )
    assert plan.total_segments == 3 and len(plan.parts) == 3
    result = assemble_translation(plan, {0: "标题", 1: "第一 \u27e60\u27e7"})
    assert result.status == "partial" and not result.complete
    assert "<h2>标题</h2><ul><li>第一 <code>code</code></li></ul>" in result.html
    assert "<p>Last</p>" in result.html and "<pre>Do not translate code</pre>" in result.html


def test_translation_batches_and_cap_are_deterministic_and_remaining_blocks_stay_original() -> None:
    source = "".join(f"<p>{'a' * 3000} {index}</p>" for index in range(25))
    plan = plan_translation(source)
    assert plan.truncated and len(plan.parts) == 19 and len(plan.batches) == 19
    assert plan.input_fingerprint == plan_translation(source).input_fingerprint
    result = assemble_translation(plan, {i: "中文" for i in range(len(plan.parts))})
    assert result.translated_segments == 19 and result.status == "partial"
    assert "<p>" + "a" * 3000 + " 24</p>" in result.html


def test_source_html_is_sanitized_without_translating_chinese_only_or_code() -> None:
    plan = plan_translation(
        '<p onclick="secret()">中文</p><script>secret()</script>'
        '<pre>code</pre><p><a href="javascript:alert(1)">Read</a></p>'
    )
    assert plan.total_segments == 1
    assert "secret" not in plan.source_html and "javascript" not in plan.source_html


def test_heading_anchors_survive_translation_without_accepting_active_attributes() -> None:
    plan = plan_translation('<h1 id="intro" onclick="bad()">Welcome</h1><h6 id="细节">Details</h6>')
    result = assemble_translation(plan, {0: "欢迎", 1: "详细内容"})
    assert result.complete
    assert '<h1 id="intro">欢迎</h1>' in result.html
    assert '<h6 id="细节">详细内容</h6>' in result.html
    assert "onclick" not in result.html


def test_responsive_images_audio_and_table_attributes_survive_translated_text() -> None:
    plan = plan_translation(
        '<input value="ignored"><table><tbody><tr><td colspan="2">Details</td></tr></tbody></table>'
        '<p>Listen <audio controls><source src="https://example.com/a.mp3" type="audio/mpeg">'
        '</audio><picture><source srcset="https://example.com/a.webp 1x, '
        'https://example.com/b.webp 2x" type="image/webp">'
        '<img src="https://example.com/a.png" srcset="javascript:bad() 2x"></picture></p>'
    )
    assert plan.total_segments == 2
    result = assemble_translation(
        plan, {0: "详情", 1: plan.parts[1].html.replace("Listen", "收听")}
    )
    assert result.complete and '<td colspan="2">详情</td>' in result.html
    assert '<audio controls="">' in result.html and 'type="audio/mpeg"' in result.html
    assert 'srcset="https://example.com/a.webp 1x, https://example.com/b.webp 2x"' in result.html
    assert 'type="image/webp"' in result.html and "javascript" not in result.html
    assert "ignored" not in result.html
