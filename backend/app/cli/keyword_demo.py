"""Run with python -m cli.keyword_demo; artifacts stay local and private."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer

from sources.keyword_demo import tick

app = typer.Typer()


@app.command()
def main(
    identity_env: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    directory: Annotated[Path, typer.Option()],
    keyword: Annotated[str, typer.Option()] = "DeepSeek",
    resume: Annotated[bool, typer.Option(help="Resume after fixing the recorded failure.")] = False,
    pause: Annotated[bool, typer.Option(help="Pause without deleting evidence.")] = False,
    watch: Annotated[
        bool, typer.Option(help="Poll due state every 30s; source interval stays 1h.")
    ] = False,
) -> None:
    """Collect once when due, or keep the same persisted schedule running."""
    while True:
        try:
            state = tick(directory, identity_env, keyword=keyword, resume=resume, pause=pause)
            resume = False
        except (OSError, ValueError):
            typer.echo("demo_configuration_or_lock_error", err=True)
            raise typer.Exit(1) from None
        typer.echo(
            json.dumps(
                {
                    "keyword": state.keyword,
                    "posts": len(state.posts),
                    "comments": len(state.comments),
                    "next_run_at": state.next_run_at.isoformat(),
                    "stopped_reason": state.stopped_reason,
                },
                ensure_ascii=False,
            )
        )
        if state.stopped_reason:
            raise typer.Exit(2)
        if not watch:
            return
        time.sleep(30)


if __name__ == "__main__":
    app()
