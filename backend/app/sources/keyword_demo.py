"""Restart-safe local evidence for the explicitly scoped keyword POC."""

from __future__ import annotations

import fcntl
import html
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from sources.adapters.bilibili_chrome import VERSION, CollectionStoppedError, collect
from sources.contracts import SourceComment, SourcePost


class DemoRun(BaseModel):
    due_at: datetime
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"
    reason: str | None = None
    request_count: int = 0
    candidates: int = 0
    posts: int = 0
    comments: int = 0
    new_posts: int = 0
    new_comments: int = 0


class DemoState(BaseModel):
    version: str = VERSION
    keyword: str = "DeepSeek"
    interval_seconds: int = Field(default=3600, ge=3600)
    next_run_at: datetime
    stopped_reason: str | None = None
    last_tick_at: datetime | None = None
    request_day: str = ""
    daily_requests: int = 0
    runs: list[DemoRun] = Field(default_factory=list)
    posts: dict[str, SourcePost] = Field(default_factory=dict)
    comments: dict[str, SourceComment] = Field(default_factory=dict)
    first_seen: dict[str, datetime] = Field(default_factory=dict)
    last_seen: dict[str, datetime] = Field(default_factory=dict)


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def render(state: DemoState) -> str:
    def escape(value: object) -> str:
        return html.escape(str(value))

    def stamp(value: datetime | None) -> str:
        return (
            value.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M:%S")
            if value
            else "未知"
        )

    items = []
    for post in sorted(
        state.posts.values(),
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    ):
        replies = [c for c in state.comments.values() if c.post_external_id == post.external_id]
        comment_html = "".join(
            f"<li><p>{escape(c.text)}</p><small>发布 {stamp(c.published_at)} · "
            f'<a href="{escape(c.canonical_url)}" target="_blank" rel="noreferrer">'
            f"评论原文</a></small></li>"
            for c in sorted(
                replies,
                key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
        )
        first_seen = stamp(state.first_seen.get("p:" + post.external_id))
        last_seen = stamp(state.last_seen.get("p:" + post.external_id))
        items.append(
            f'<article><h2><a href="{escape(post.canonical_url)}" target="_blank" rel="noreferrer">'
            f"{escape(post.title)}</a></h2><p>{escape(post.text)}</p>"
            f"<small>发布 {stamp(post.published_at)} · 首见 {first_seen}"
            f" · 最近采集 {last_seen}</small>"
            f'<p class="tag">标题或摘要包含 {escape(state.keyword)} · 搜索摘要 · 根评论抽样</p>'
            f"<details><summary>已采集 {len(replies)} 条评论</summary>"
            f"<ol>{comment_html}</ol></details></article>"
        )
    rows = "".join(
        f"<tr><td>{stamp(run.due_at)}</td><td>{stamp(run.started_at)}</td>"
        f"<td>{escape(run.status)} / {escape(run.reason or '—')}</td>"
        f"<td>{run.posts} / {run.comments}</td><td>{run.new_posts} / {run.new_comments}</td>"
        f"<td>{run.request_count}</td></tr>"
        for run in reversed(state.runs[-30:])
    )
    status = f"已暂停: {state.stopped_reason}" if state.stopped_reason else "已配置定时采集"
    template = Path(__file__).with_suffix(".html").read_text()
    values = {
        "KEYWORD": escape(state.keyword),
        "STATUS": escape(status),
        "HOURS": str(state.interval_seconds // 3600),
        "NEXT": stamp(state.next_run_at),
        "CHECKED": stamp(state.last_tick_at),
        "POSTS": str(len(state.posts)),
        "COMMENTS": str(len(state.comments)),
        "REQUESTS": str(state.daily_requests),
        "ROWS": rows,
        "ITEMS": "".join(items) or "<section>尚无成功采集的相关帖子, 请查看运行记录。</section>",
    }
    for key, value in values.items():
        template = template.replace("__" + key + "__", value)
    return template


def tick(
    directory: Path,
    identity_env: Path,
    *,
    keyword: str = "DeepSeek",
    resume: bool = False,
    pause: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    collector: Callable[..., tuple[list[SourcePost], list[SourceComment], int]] = collect,
) -> DemoState:
    if (
        not keyword.strip()
        or keyword != keyword.strip()
        or len(keyword) > 80
        or any(ord(c) < 32 for c in keyword)
    ):
        raise ValueError("invalid keyword")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("demo directory must be private")
    lock = directory / ".lock"
    lock.touch(mode=0o600, exist_ok=True)
    with lock.open("r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory / "state.json"
        now = clock()
        state = (
            DemoState.model_validate_json(path.read_text())
            if path.exists()
            else DemoState(keyword=keyword, next_run_at=now)
        )
        state.last_tick_at = now
        if state.keyword != keyword or state.version != VERSION:
            raise ValueError("use a separate directory for a changed keyword or adapter")

        def save() -> None:
            cutoff = now - timedelta(days=30)
            expired = {key for key, seen in state.last_seen.items() if seen < cutoff}
            for key in expired:
                state.first_seen.pop(key, None)
                state.last_seen.pop(key, None)
                if key.startswith("p:"):
                    state.posts.pop(key[2:], None)
                else:
                    state.comments.pop(key[2:], None)
            atomic_write(path, state.model_dump_json(indent=2))
            atomic_write(directory / "index.html", render(state))

        if state.runs and state.runs[-1].status == "running":
            state.runs[-1].status = "interrupted"
            state.runs[-1].reason = "process_interrupted"
            state.stopped_reason = "process_interrupted"
        if pause:
            state.stopped_reason = "operator_paused"
        elif resume:
            state.stopped_reason = None
        if state.stopped_reason or now < state.next_run_at:
            save()
            return state
        local = now.astimezone(ZoneInfo("Asia/Shanghai"))
        if local.hour < 8:
            state.next_run_at = local.replace(hour=8, minute=0, second=0, microsecond=0).astimezone(
                UTC
            )
            save()
            return state
        day = local.date().isoformat()
        if state.request_day != day:
            state.request_day, state.daily_requests = day, 0
        if state.daily_requests + 4 > 60:
            state.next_run_at = (
                (local + timedelta(days=1))
                .replace(hour=8, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
            )
            save()
            return state
        run = DemoRun(due_at=state.next_run_at, started_at=now)
        state.runs.append(run)
        state.runs = state.runs[-200:]
        # Persist before network access: crashes cannot cause immediate duplicate requests.
        state.next_run_at = now + timedelta(seconds=state.interval_seconds)
        save()

        def charge() -> None:
            if run.request_count >= 4 or state.daily_requests >= 60:
                raise CollectionStoppedError("request_budget_exhausted")
            run.request_count += 1
            state.daily_requests += 1
            save()

        try:
            posts, comments, candidates = collector(
                identity_env=identity_env,
                keyword=keyword,
                starts_at=now - timedelta(hours=72),
                ends_at=now,
                charge=charge,
            )
            observed = clock()
            run.candidates, run.posts, run.comments = candidates, len(posts), len(comments)
            for item in posts:
                run.new_posts += int(item.external_id not in state.posts)
                state.posts[item.external_id] = item
                key = "p:" + item.external_id
                state.first_seen.setdefault(key, observed)
                state.last_seen[key] = observed
            for comment in comments:
                run.new_comments += int(comment.external_id not in state.comments)
                state.comments[comment.external_id] = comment
                key = "c:" + comment.external_id
                state.first_seen.setdefault(key, observed)
                state.last_seen[key] = observed
            run.status = "sampled" if posts else "empty"
        except CollectionStoppedError as error:
            run.status, run.reason = "stopped", str(error)
            state.stopped_reason = str(error)
        except Exception:
            run.status, run.reason = "stopped", "unexpected_collection_error"
            state.stopped_reason = run.reason
        run.finished_at = clock()
        save()
        return state
