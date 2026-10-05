"""Controlled DTOs verify outlet guard ordering; real persistence is tested separately."""

from fastapi.testclient import TestClient

from api.dependencies import get_publication_service, require_public_distribution_limit
from core.errors import ApplicationError
from publication.exports import item_markdown, list_markdown, render_rss
from publication.schemas import PublicItemsPage
from tests.unit.test_publication_exports import detail


def test_http_outlets_recheck_reader_before_old_etag_and_refuse_withdrawn_dtos(app):
    current = detail()
    withdrawn, calls = False, []

    class ControlledReading:
        def guarded(self):
            calls.append(current.revision)
            if withdrawn:
                raise ApplicationError("resource_not_found")
            return current

        def detail(self, **kwargs):
            return self.guarded()

        def feed(self, **kwargs):
            return render_rss(
                [self.guarded()],
                origin="https://hotkey.example",
                self_path="/public/feed.xml",
                title="精选",
                now=current.timeline_at,
            )

        def markdown(self, **kwargs):
            return item_markdown(self.guarded(), origin="https://hotkey.example")

        def latest_markdown(self, **kwargs):
            return list_markdown([self.guarded()], title="精选", origin="https://hotkey.example")

        def share_item(self, **kwargs):
            return self.guarded().title.encode()

        def items(self, **kwargs):
            return PublicItemsPage(
                items=[self.guarded()], next_cursor=None, snapshot_at=current.timeline_at
            )

    app.state.settings.public_publication_owner_id = current.id
    app.dependency_overrides[get_publication_service] = lambda: ControlledReading()
    app.dependency_overrides[require_public_distribution_limit] = lambda: None
    client = TestClient(app)
    paths = [
        f"/public/api/items/{current.id}",
        "/public/api/items",
        "/public/feed.xml",
        f"/public/items/{current.id}.md",
        "/public/selected.md",
        f"/og/items/{current.id}.png",
    ]
    try:
        original = {path: client.get(path) for path in paths}
        assert all(response.status_code == 200 for response in original.values())
        for path, response in original.items():
            previous_calls = len(calls)
            cached = client.get(path, headers={"If-None-Match": response.headers["etag"]})
            assert cached.status_code == 304 and not cached.content
            assert cached.headers["cache-control"] == "no-store"
            assert len(calls) == previous_calls + 1
        current = current.model_copy(
            update={"revision": 2, "title": "更正标题", "summary": "更正摘要"}
        )
        corrected = {}
        for path, response in original.items():
            corrected[path] = client.get(path, headers={"If-None-Match": response.headers["etag"]})
            assert corrected[path].status_code == 200
            assert corrected[path].headers["etag"] != response.headers["etag"]
            assert corrected[path].headers["cache-control"] == "no-store"
        withdrawn = True
        for path, response in corrected.items():
            previous_calls = len(calls)
            assert (
                client.get(path, headers={"If-None-Match": response.headers["etag"]}).status_code
                == 404
            )
            assert len(calls) == previous_calls + 1
    finally:
        app.dependency_overrides.clear()
