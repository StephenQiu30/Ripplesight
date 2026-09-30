from __future__ import annotations

import os

RSSHUB_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})


def configured_rsshub_host() -> str:
    host = os.environ.get("HOTKEY_RSSHUB_HOST", "127.0.0.1")
    if host not in RSSHUB_HOSTS:
        raise ValueError("HOTKEY_RSSHUB_HOST must be a fixed local RSSHub host")
    return host


def is_fixed_rsshub_endpoint(url: str, *, route: str, allowed_hosts: frozenset[str]) -> bool:
    return any(
        allowed_hosts == frozenset({host}) and url == f"http://{host}:1200{route}"
        for host in RSSHUB_HOSTS
    )
