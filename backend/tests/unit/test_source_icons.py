from sources.icons import home_of, icon_candidates, mp_avatar


def test_icon_candidates_preserve_upstream_priority_dedupe_and_favicon():
    html = (
        '<link rel="icon" href="/favicon.ico"><link rel="icon" sizes="512x512" href="/large.png">'
        '<link rel="icon" href="/vector.svg"><link rel="apple-touch-icon" href="/touch.png">'
        '<link rel="icon" href="data:image/png;base64,AA"><link rel="icon" href="/touch.png">'
    )
    assert icon_candidates(html, "https://example.com/home") == (
        "https://example.com/touch.png",
        "https://example.com/large.png",
        "https://example.com/vector.svg",
        "https://example.com/favicon.ico",
    )


def test_home_uses_seventy_percent_of_latest_urls_and_otherwise_configured_origin():
    one = [f"https://example.com/{i}" for i in range(7)]
    other = [f"https://other.com/{i}" for i in range(3)]
    assert home_of((*one, *other), {"url": "https://fallback.com/news"}) == "https://example.com"
    assert (
        home_of(
            (*one[:6], *other, "https://third.com/x"),
            {"feed_url": "https://r.jina.ai/https://fallback.com/feed"},
        )
        == "https://fallback.com"
    )
    assert home_of((), {"url": "http://127.0.0.1/private"}) is None


def test_mp_avatar_is_public_https_from_declared_account_field_only():
    assert mp_avatar('var round_head_img = "http://example.com/avatar.png";') == (
        "https://example.com/avatar.png"
    )
    assert mp_avatar('<img src="https://example.com/article.jpg">') is None
    assert mp_avatar('round_head_img: "http://127.0.0.1/icon"') is None
