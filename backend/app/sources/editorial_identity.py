"""Pinned original-permalink candidates; these facts never authorize collection or merging."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, Self
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from pydantic import Field, model_validator

from sources.editorial_base import EditorialContract
from sources.editorial_rsshub import RSSHUB_REVISION, rsshub_route_blocker

if TYPE_CHECKING:
    from sources.editorial_schemas import EditorialMaterial, EditorialSourceConfiguration

NATIVE_IDENTITY_PURPOSE = "hotkey:native-object-dedup:v1"
_THREADS_PERMALINK = re.compile(r"https://www\.threads\.com/t/([A-Za-z0-9_-]{1,128})")
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
_XML_ENCODING = re.compile(r'<\?xml\s+[^?]*\bencoding\s*=\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE)


class EditorialNativeIdentityProof(EditorialContract):
    """A bounded parser fact. Only a rechecked internal source Job can admit it."""

    schema_version: Literal["rsshub-original-permalink-v1"] = "rsshub-original-permalink-v1"
    platform: Literal["threads"] = "threads"
    object_type: Literal["post"] = "post"
    namespace: Literal["threads_shortcode"] = "threads_shortcode"
    native_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    proof_kind: Literal["rsshub_original_permalink_v1"] = "rsshub_original_permalink_v1"
    canonical_object_url: str = Field(min_length=1, max_length=512)
    collector_revision: str = Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$")
    route_key: str = Field(min_length=2, max_length=1024)
    query_mode: Literal["author_stream", "tag_feed", "platform_keyword"]
    configuration_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    evidence_field: Literal["rss2:item/link"] = "rss2:item/link"

    @model_validator(mode="after")
    def exact_original_permalink(self) -> Self:
        match = _THREADS_PERMALINK.fullmatch(self.canonical_object_url)
        if (
            match is None
            or match[1] != self.native_id
            or self.collector_revision != RSSHUB_REVISION
        ):
            raise ValueError("native proof requires the pinned exact original Threads permalink")
        return self


def _configuration_digest(configuration: EditorialSourceConfiguration) -> str:
    # The shared schema imports this DTO. Resolve its existing digest only when
    # executing the pure function, after both modules have initialized.
    from sources.editorial_schemas import fingerprint

    return fingerprint(configuration.model_dump(mode="json")).hex()


def _candidate_configuration(configuration: EditorialSourceConfiguration) -> bool:
    from pydantic import ValidationError

    from sources.editorial_schemas import EditorialSourceConfiguration

    try:
        EditorialSourceConfiguration.model_validate(configuration.model_dump())
    except ValidationError:
        return False
    rsshub = configuration.rsshub
    return bool(
        configuration.kind == "rss"
        and rsshub is not None
        and rsshub.platform == "threads"
        and rsshub_route_blocker(rsshub) is None
        and configuration.item_url_prefix_rewrite is None
        and not configuration.preserve_url_fragment
    )


def _unshared_root_description(description: str, author: str) -> bool:
    # The pinned route always emits a blockquote for shared posts. Do not select
    # their embedded links, even when malformed provider HTML obscures the DOM.
    if not author or re.search(r"<\s*blockquote\b", description, re.IGNORECASE):
        return False
    soup = BeautifulSoup(description, "html.parser")
    nodes = [node for node in soup.contents if not isinstance(node, str) or node.strip()]
    if not nodes or not isinstance(nodes[0], Tag) or nodes[0].name != "p":
        return False
    header = nodes[0]
    if header.attrs or len(header.contents) != 2:
        return False
    name, suffix = header.contents
    return bool(
        isinstance(name, Tag)
        and name.name == "strong"
        and not name.attrs
        and len(name.contents) == 1
        and isinstance(name.contents[0], NavigableString)
        and str(name.contents[0]) == f"@{author}"
        and isinstance(suffix, NavigableString)
        and str(suffix) == ":"
    )


def rsshub_native_identity_proofs(
    text: str | bytes,
    *,
    configuration: EditorialSourceConfiguration,
    parsed_links: tuple[str | None, ...],
) -> tuple[EditorialNativeIdentityProof | None, ...]:
    """Align original RSS2 fields with parsed entries before any URL rewriting.

    Unknown structures retain the ordinary profile-scoped identity. This pure
    function neither grants server approval nor performs a provider request.
    """
    unknown: tuple[EditorialNativeIdentityProof | None, ...] = (None,) * len(parsed_links)
    if not _candidate_configuration(configuration):
        return unknown
    try:
        decoded = text if isinstance(text, str) else text.decode("utf-8", errors="strict")
    except UnicodeError:
        return unknown
    # The fixed emitter produces UTF-8 RSS2. Do not let a differently encoded
    # DTD evade an ASCII byte scan or reinterpret a candidate's original fields.
    declared_encoding = _XML_ENCODING.search(decoded)
    if (
        "\x00" in decoded
        or (declared_encoding is not None and declared_encoding[1].casefold() != "utf-8")
        or "<!DOCTYPE" in decoded.upper()
        or "<!ENTITY" in decoded.upper()
    ):
        return unknown
    try:
        root = ElementTree.fromstring(decoded)
    except ElementTree.ParseError:
        return unknown
    channels = root.findall("channel")
    if (
        root.tag != "rss"
        or root.attrib.get("version") != "2.0"
        or len(channels) != 1
        or any(_XML_BASE in element.attrib for element in root.iter())
    ):
        return unknown
    items = channels[0].findall("item")
    if len(items) != len(parsed_links):
        return unknown
    rsshub = configuration.rsshub
    assert rsshub is not None
    digest = _configuration_digest(configuration)
    proofs: list[EditorialNativeIdentityProof | None] = []
    for item, parsed_link in zip(items, parsed_links, strict=True):
        links, authors, descriptions = (
            item.findall("link"),
            item.findall("author"),
            item.findall("description"),
        )
        if (
            len(links) != 1
            or len(authors) != 1
            or len(descriptions) != 1
            or any(len(element) or element.attrib for element in (*links, *authors, *descriptions))
        ):
            proofs.append(None)
            continue
        link, author, description = links[0].text, authors[0].text, descriptions[0].text
        match = _THREADS_PERMALINK.fullmatch(link or "")
        if (
            match is None
            or link != parsed_link
            or not _unshared_root_description(description or "", author or "")
        ):
            proofs.append(None)
            continue
        proofs.append(
            EditorialNativeIdentityProof(
                native_id=match[1],
                canonical_object_url=match[0],
                collector_revision=rsshub.revision,
                route_key=rsshub.route,
                query_mode=rsshub.query_mode,
                configuration_sha256=digest,
            )
        )
    return tuple(proofs)


def verify_editorial_native_identity(
    material: EditorialMaterial,
    *,
    configuration: EditorialSourceConfiguration,
) -> EditorialNativeIdentityProof | None:
    """Check candidate consistency; the caller must separately recheck Job authority."""
    from pydantic import ValidationError

    from sources.editorial_schemas import EditorialSourceConfiguration

    if material.native_identity is None:
        return None
    try:
        # Revalidate copies instead of trusting model_copy/update or an already
        # typed DTO as proof of valid frozen state.
        configuration = EditorialSourceConfiguration.model_validate(configuration.model_dump())
        proof = EditorialNativeIdentityProof.model_validate(material.native_identity.model_dump())
    except ValidationError:
        return None
    rsshub = configuration.rsshub
    if not _candidate_configuration(configuration) or rsshub is None:
        return None
    if (
        material.external_id is not None
        or material.url != proof.canonical_object_url
        or material.identity_key != f"url:{proof.canonical_object_url}"
        or proof.collector_revision != rsshub.revision
        or proof.route_key != rsshub.route
        or proof.query_mode != rsshub.query_mode
        or proof.configuration_sha256 != _configuration_digest(configuration)
        or material.metadata.get("collector") != "rsshub"
        or material.metadata.get("collector_revision") != rsshub.revision
        or material.metadata.get("query_mode") != rsshub.query_mode
    ):
        return None
    return proof
