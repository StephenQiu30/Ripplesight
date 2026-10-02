from jobs.source_scopes import collection_selector_reference


def test_original_scope_is_exact_and_never_platform_or_author_wide():
    target = "a1" * 32
    assert (
        collection_selector_reference("keyword.search", "hackernews", {"target_hash": target})
        == f"search:{target}"
    )
    assert (
        collection_selector_reference("source.comments", "hackernews", {"target_hash": target})
        == f"comments:{target}"
    )
    assert collection_selector_reference("source.hotlist", "weibo", {}) == "hotlist:weibo"
    first = collection_selector_reference(
        "webpage.collect", "web", {"target_url": "https://example.com/a"}
    )
    second = collection_selector_reference(
        "webpage.collect", "web", {"target_url": "https://example.com/b"}
    )
    assert first and first.startswith("page:") and first != second
    assert (
        collection_selector_reference("keyword.search", "hackernews", {"target_hash": "bad"})
        is None
    )
    assert collection_selector_reference("source.author", "x", {"author": "a"}) is None
