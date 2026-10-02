from uuid import uuid4

import httpx
from pydantic import SecretStr

from jobs.editorial_schemas import EditorialGroupManifest, EditorialGroupMember
from sources.adapters.editorial_x import OfficialEditorialXClient
from sources.editorial_group_collect import collect_editorial_group
from sources.editorial_schemas import EditorialCursor, fingerprint
from tests.unit.test_editorial_sources import NOW, admitted_http, config, profile


def controlled_group():
    profiles = tuple(
        profile(config("x_search", query=f"from:{name}")).model_copy(
            update={"source_key": "ed_x_search_" + ident.hex, "id": ident}
        )
        for name, ident in ((name, uuid4()) for name in ("one", "two"))
    )
    cursors = {
        p.id: EditorialCursor(initialized_at=NOW, last_tweet_id="100", last_ok_at=NOW)
        for p in profiles
    }
    members = tuple(
        EditorialGroupMember(
            profile_id=p.id,
            source_key=p.source_key,
            configuration_version=1,
            revision=1,
            policy_version=1,
            configuration_sha256=fingerprint(p.configuration.model_dump(mode="json")).hex(),
            handle=name,
            cursor_json=cursors[p.id].model_dump_json(),
        )
        for name, p in zip(("one", "two"), profiles, strict=True)
    )
    manifest = EditorialGroupManifest(
        owner_id=uuid4(),
        connection_id=uuid4(),
        connection_version=1,
        participation_mode="editorial",
        query="(from:one OR from:two) -is:reply",
        since_id="100",
        members=members,
    )
    return manifest, {p.id: (p, cursors[p.id], {}) for p in profiles}


def test_actual_group_http_demultiplexes_authors_and_freezes_page_backlog():
    manifest, inputs = controlled_group()
    requests = []
    costs = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "200",
                        "text": "One post",
                        "author_id": "1",
                        "created_at": NOW.isoformat(),
                    }
                ],
                "includes": {"users": [{"id": "1", "username": "one"}]},
                "meta": {"next_token": "next"},
            },
        )

    http, _ = admitted_http(handler, hosts=("api.x.com",))
    pages = collect_editorial_group(
        manifest,
        inputs,
        OfficialEditorialXClient(http, bearer=SecretStr("controlled")),
        now=NOW,
        report_cost=lambda n, c: costs.append((n, c)),
        fresh_pages=1,
        backlog_pages=1,
    )
    first, second = (pages[m.profile_id] for m in manifest.members)
    assert len(requests) == 1 and costs == [
        (1, {manifest.members[0].source_key: 1, manifest.members[1].source_key: 0})
    ]
    assert first.materials[0].body_text == "One post" and not second.materials
    assert first.status == second.status == "partial"
    assert first.cursor.last_tweet_id == "200" and second.cursor.last_tweet_id == "100"
    assert (
        first.cursor.x_backlog[0].query == manifest.query
        and first.cursor.x_backlog[0].next_token == "next"
    )
    assert first.cursor.x_backlog[0].group_manifest_json == manifest.model_dump_json()
    http.close()


def test_group_response_with_unfrozen_author_is_unknown_and_no_clock_advance():
    manifest, inputs = controlled_group()
    costs = []
    http, _ = admitted_http(
        lambda request: httpx.Response(
            200,
            json={
                "data": [{"id": "200", "text": "Other", "author_id": "3"}],
                "includes": {"users": [{"id": "3", "username": "other"}]},
            },
        ),
        hosts=("api.x.com",),
    )
    pages = collect_editorial_group(
        manifest,
        inputs,
        OfficialEditorialXClient(http, bearer=SecretStr("controlled")),
        now=NOW,
        report_cost=lambda n, c: costs.append((n, c)),
    )
    assert costs == [(None, None)] and http.request_count == 1
    assert all(p.status == "unknown" and p.cursor.last_tweet_id == "100" for p in pages.values())
    http.close()


def test_group_resumes_original_token_and_member_set_instead_of_solo_query():
    from sources.editorial_schemas import SearchBacklog

    manifest, inputs = controlled_group()
    gap = SearchBacklog(
        query=manifest.query,
        next_token="saved",
        stop_at_id="90",
        group_manifest_json=manifest.model_dump_json(),
    )
    inputs = {
        i: (p, c.model_copy(update={"x_backlog": (gap,)}), k) for i, (p, c, k) in inputs.items()
    }
    requests = []
    http, _ = admitted_http(
        lambda request: requests.append(request) or httpx.Response(200, json={"data": []}),
        hosts=("api.x.com",),
    )
    pages = collect_editorial_group(
        manifest,
        inputs,
        OfficialEditorialXClient(http, bearer=SecretStr("controlled")),
        now=NOW,
        report_cost=lambda count, allocation: None,
    )
    assert len(requests) == 2
    assert (
        requests[1].url.params["next_token"] == "saved"
        and requests[1].url.params["query"] == manifest.query
    )
    assert requests[1].url.params["since_id"] == "90"
    assert all(
        p.status == "complete" and not p.cursor.x_backlog and p.cursor.last_ok_at == NOW
        for p in pages.values()
    )
    http.close()
