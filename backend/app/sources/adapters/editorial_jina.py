"""Explicit Jina Reader paid boundary with approved targets and original ledger hooks."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr

from sources.adapters.editorial_http import (
    EditorialHttpClient,
    EditorialHttpResponse,
    EditorialSourceError,
)
from sources.editorial_schemas import public_url


class EditorialJinaReader:
    def __init__(
        self,
        http: EditorialHttpClient,
        *,
        key: SecretStr,
        allowed_targets: frozenset[str],
        before_paid: Callable[[str], bool],
        report_cost: Callable[[str, Decimal | None], None],
        cny_per_million_tokens: Decimal | None = None,
    ) -> None:
        self._http, self._key, self._targets, self._before, self._report, self._unit = (
            http,
            key,
            allowed_targets,
            before_paid,
            report_cost,
            cny_per_million_tokens,
        )
        if cny_per_million_tokens is not None and (
            not cny_per_million_tokens.is_finite() or cny_per_million_tokens <= 0
        ):
            raise ValueError("approved Jina token quote must be positive")

    def read(
        self, url: str, *, format: Literal["html", "markdown"], cache_tolerance: int | None = None
    ) -> EditorialHttpResponse:
        target = public_url(url.removeprefix("https://r.jina.ai/"))
        if urlsplit(target).hostname not in self._targets:
            raise EditorialSourceError("unapproved_target", blocked=True)
        if not self._before("jina_listing"):
            raise EditorialSourceError("budget_exhausted", blocked=True)
        previous_requests = self._http.request_count
        headers = {
            "authorization": "Bearer " + self._key.get_secret_value(),
            "x-return-format": format,
            "accept": "text/plain",
        }
        if cache_tolerance is not None:
            headers["x-cache-tolerance"] = str(cache_tolerance)
        try:
            response = self._http.request(
                "https://r.jina.ai/" + target, headers=headers, same_origin_redirects=True
            )
            tokens = response.headers.get("x-usage-tokens")
            amount = None
            if tokens and re.fullmatch(r"[0-9]{1,12}", tokens) and self._unit is not None:
                amount = Decimal(tokens) * self._unit / Decimal(1000000)
            self._report("jina_listing", amount)
            text = response.text
            if format == "markdown" and "\nMarkdown Content:\n" in text:
                text = text.split("\nMarkdown Content:\n", 1)[1]
            return EditorialHttpResponse(target, response.status, response.headers, text.encode())
        except EditorialSourceError:
            self._report(
                "jina_listing",
                Decimal(0) if self._http.request_count == previous_requests else None,
            )
            raise
