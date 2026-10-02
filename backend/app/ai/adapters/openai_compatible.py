"""Protected OpenAI-compatible structured calls; one request with no automatic retries."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx

from ai.capability_schemas import AiModelServerSpec
from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiImageInput, AiTokenUsage


class OpenAiCompatibleClient:
    def __init__(
        self,
        spec: AiModelServerSpec,
        *,
        enabled: bool,
        transport: httpx.BaseTransport | None = None,
        before_request: Callable[[], None] | None = None,
    ) -> None:
        self.spec, self.enabled, self.before_request = spec, enabled, before_request
        self.provider, self.model, self.component_key = (
            spec.provider_key,
            spec.model,
            spec.component_key,
        )
        self._http = httpx.Client(
            timeout=spec.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        return self.complete_multimodal(
            prompt=prompt, output_schema=output_schema, instructions=instructions, images=()
        )

    def complete_multimodal(
        self,
        *,
        prompt: str,
        output_schema: Mapping[str, Any],
        instructions: str = "",
        images: Sequence[AiImageInput] = (),
    ) -> AiCompletion:
        if not self.enabled or not self.spec.configured:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "compatible model requests are disabled")
        if images and not self.spec.vision:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "selected model has no vision support")
        messages: list[dict[str, Any]] = []
        if instructions:
            messages.append({"role": "system", "content": instructions})
        content: str | list[dict[str, Any]] = prompt
        if images:
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": image.data_url}} for image in images[:1]
            ]
        messages.append({"role": "user", "content": content})
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.spec.max_output_tokens,
            **self.spec.extra,
        }
        if self.spec.json_mode:
            payload["response_format"] = {"type": "json_object"}
        # A schema is part of the request, including JSON mode providers that ignore JSON Schema.
        messages.insert(
            0,
            {
                "role": "system",
                "content": "Return only a JSON object matching this schema: "
                + json.dumps(dict(output_schema), ensure_ascii=False, allow_nan=False),
            },
        )
        started = time.monotonic()
        if self.before_request:
            self.before_request()
        assert self.spec.base_url is not None and self.spec.api_key is not None
        try:
            with self._http.stream(
                "POST",
                self.spec.base_url.rstrip("/") + "/chat/completions",
                headers={"authorization": "Bearer " + self.spec.api_key.get_secret_value()},
                json=payload,
            ) as response:
                if response.status_code == 429:
                    raise AiCallError(
                        AiFailureCode.RATE_LIMITED, "compatible provider rate limited"
                    )
                if not 200 <= response.status_code < 300:
                    raise AiCallError(
                        AiFailureCode.UNAVAILABLE, "compatible provider rejected request"
                    )
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 10_000_000:
                        raise AiCallError(
                            AiFailureCode.INVALID_OUTPUT, "compatible response exceeds limit"
                        )
        except httpx.TimeoutException:
            raise AiCallError(
                AiFailureCode.TIMEOUT, "compatible response is unknown", outcome_unknown=True
            ) from None
        except httpx.TransportError:
            raise AiCallError(
                AiFailureCode.UNAVAILABLE,
                "compatible request outcome is unknown",
                outcome_unknown=True,
            ) from None
        try:
            value = json.loads(raw)
            answer = value["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or len(answer) > 5_000_000:
                raise ValueError
            text = answer.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            output = json.loads(text)
            if not isinstance(output, dict):
                raise ValueError
            usage = value.get("usage")
            usage_reported = isinstance(usage, dict) and all(
                type(usage.get(name)) is int for name in ("prompt_tokens", "completion_tokens")
            )
            if not isinstance(usage, dict):
                usage = {}
            details = usage.get("prompt_tokens_details") or {}
            result = AiCompletion(
                provider=self.provider,
                model=self.model,
                output=output,
                usage=AiTokenUsage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    cached_input_tokens=details.get("cached_tokens", 0)
                    if isinstance(details, dict)
                    else 0,
                    output_tokens=usage.get("completion_tokens", 0),
                ),
                duration_ms=int((time.monotonic() - started) * 1000),
                usage_reported=usage_reported,
            )
        except (KeyError, TypeError, ValueError, IndexError):
            raise AiCallError(
                AiFailureCode.INVALID_OUTPUT, "compatible response is not usable structured JSON"
            ) from None
        return result
