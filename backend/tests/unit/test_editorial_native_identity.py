from datetime import UTC, datetime, timedelta
from html import escape
from uuid import uuid4

import pytest
from pydantic import ValidationError

from connections.editorial_schemas import ExternalEditorialInput, external_native_identity_claim
from connections.external_ingress import prepare_external_materials
from sources.adapters.editorial_http import EditorialSourceError
from sources.adapters.editorial_rss import parse_feed
from sources.editorial_identity import (
    EditorialNativeIdentityProof,
    rsshub_native_identity_proofs,
    verify_editorial_native_identity,
)
from sources.editorial_rsshub import RSSHUB_REVISION
from sources.editorial_schemas import EditorialSourceConfiguration

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def config(**values: object) -> EditorialSourceConfiguration:
    rsshub = {
        "platform": "threads",
        "query_mode": "author_stream",
        "target": "sample",
        "route": "/threads/sample",
        "revision": RSSHUB_REVISION,
        "item_hosts": ["www.threads.com"],
        "downstream_hosts": ["www.threads.com"],
        "text_scope": "post_text",
        "max_downstream_requests": 1,
        "cache_ttl_seconds": 300,
        "review": {
            "purpose_reference": "evidence://purpose",
            "downstream_reference": "trace://egress",
            "cache_reference": "deployment://cache",
            "fee_reference": "evidence://zero-fee",
            "stop_reference": "test://stop",
            "deployment_reference": "deployment://fixed-service",
            "reviewed_at": NOW,
            "expires_at": NOW + timedelta(days=7),
        },
        **values,
    }
    return EditorialSourceConfiguration.model_validate(
        {
            "kind": "rss",
            "allowed_hosts": ["127.0.0.1"],
            "rsshub": rsshub,
            "feed_url": "http://127.0.0.1:1200" + str(rsshub["route"]),
        }
    )


def feed(
    url: str = "https://www.threads.com/t/AbC_012-",
    *,
    guid: str = "weak-feed-guid",
    description: str = "<p><strong>@sample</strong>:</p><p>Observed original text</p>",
    extra_item: str = "",
    root_attributes: str = "",
) -> str:
    return (
        f'<rss version="2.0" {root_attributes}><channel><title>Snapshot</title>'
        "<link>https://www.threads.com/@sample</link><description>Snapshot</description>"
        f"<item><title>@sample: Observed original text</title><link>{escape(url)}</link>"
        f'<guid isPermaLink="false">{escape(guid)}</guid><author>sample</author>'
        f"<description><![CDATA[{description}]]></description>{extra_item}</item>"
        "</channel></rss>"
    )


def test_original_root_permalink_has_namespaced_proof_without_relabeling_guid():
    configuration = config()
    material = parse_feed(feed(), configuration.feed_url, configuration)[0]
    proof = verify_editorial_native_identity(material, configuration=configuration)
    assert proof is not None
    assert proof.namespace == "threads_shortcode" and proof.native_id == "AbC_012-"
    assert proof.canonical_object_url == material.url
    assert material.external_id is None
    assert material.identity_key == "url:https://www.threads.com/t/AbC_012-"
    assert material.metadata["feed_guid"] == "weak-feed-guid"


def test_repost_root_and_embedded_permalink_never_create_a_strong_proof():
    configuration = config()
    shared = (
        "<p><strong>@sample</strong> 🔁:</p><p>Quoted text</p>"
        '<blockquote><a href="https://www.threads.com/t/OtherCode">Original</a></blockquote>'
    )
    material = parse_feed(feed(description=shared), configuration.feed_url, configuration)[0]
    assert material.native_identity is None
    assert verify_editorial_native_identity(material, configuration=configuration) is None


@pytest.mark.parametrize(
    ("query_mode", "route"),
    [
        ("author_stream", "/threads/sample"),
        ("platform_keyword", "/threads/search/sample/serpType=default"),
        ("platform_keyword", "/threads/search/sample/serpType=recent"),
        ("tag_feed", "/threads/search/sample"),
        ("tag_feed", "/threads/search/sample/serpType=tags"),
    ],
)
def test_allowed_entries_keep_same_case_sensitive_key_and_freeze_exact_route(query_mode, route):
    configuration = config(query_mode=query_mode, route=route)
    material = parse_feed(feed(guid="999999999"), configuration.feed_url, configuration)[0]
    proof = verify_editorial_native_identity(material, configuration=configuration)
    assert proof is not None
    assert (proof.platform, proof.object_type, proof.namespace, proof.native_id) == (
        "threads",
        "post",
        "threads_shortcode",
        "AbC_012-",
    )
    assert proof.route_key == route and proof.query_mode == query_mode
    assert material.external_id is None
    changed = parse_feed(
        feed(url="https://www.threads.com/t/aBc_012-"), configuration.feed_url, configuration
    )[0]
    assert changed.native_identity.native_id != proof.native_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.threads.com/t/AbC_012-?utm_source=feed",
        "https://www.threads.com/t/AbC_012-?x=1",
        "https://www.threads.com/t/AbC_012-#fragment",
        "http://www.threads.com/t/AbC_012-",
        "https://www.threads.com:443/t/AbC_012-",
        "https://www.threads.com/t/AbC_012-/",
        "https://www.threads.com/t//AbC_012-",
        "https://www.threads.com/t/%41bC_012-",
        "https://www.threads.com/t/中文",
        "https://www.threads.com/@sample/post/AbC_012-",
        " https://www.threads.com/t/AbC_012- ",
    ],
)
def test_url_cleanup_or_other_permalink_formats_never_mint_identity(url):
    configuration = config()
    material = parse_feed(feed(url=url), configuration.feed_url, configuration)[0]
    assert material.native_identity is None
    assert verify_editorial_native_identity(material, configuration=configuration) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://threads.com/t/AbC_012-",
        "https://www.threads.net/t/AbC_012-",
        "https://www.threads.com.evil.test/t/AbC_012-",
    ],
)
def test_off_host_links_preserve_existing_target_rejection(url):
    configuration = config()
    with pytest.raises(EditorialSourceError, match="rsshub_item_target_unapproved"):
        parse_feed(feed(url=url), configuration.feed_url, configuration)


@pytest.mark.parametrize(
    "description",
    [
        "<p><strong>@sample</strong> ↩️:</p><p>Reply</p>",
        "<p><strong>@sample</strong> replied:</p><p>Reply</p>",
        "<p><strong>@sample</strong> quoted:</p><p>Share</p>",
        "<p>Caption without source author header</p>",
        "<p><strong>@other</strong>:</p><p>Wrong root author</p>",
        "<p><strong>@sample</strong>:</p><BLOCKQUOTE>Shared text</BLOCKQUOTE>",
        "<p><strong>@sample</strong>:</p><blockquote><p>Broken share",
    ],
)
def test_shared_reply_or_ambiguous_root_description_stays_profile_scoped(description):
    configuration = config()
    material = parse_feed(feed(description=description), configuration.feed_url, configuration)[0]
    assert material.native_identity is None
    assert material.identity_key == "url:https://www.threads.com/t/AbC_012-"


def test_relative_xml_base_and_duplicate_links_cannot_be_normalized_into_a_proof():
    configuration = config()
    base = 'xml:base="https://www.threads.com"'
    material = parse_feed(
        feed(url="/t/AbC_012-", root_attributes=base), configuration.feed_url, configuration
    )[0]
    assert material.url == "https://www.threads.com/t/AbC_012-"
    assert material.native_identity is None
    for extra in (
        "<link>https://www.threads.com/t/OtherCode</link>",
        "<author>other</author>",
    ):
        material = parse_feed(feed(extra_item=extra), configuration.feed_url, configuration)[0]
        assert material.native_identity is None
    links = ("https://www.threads.com/t/AbC_012-",) * 2
    assert rsshub_native_identity_proofs(
        feed(), configuration=configuration, parsed_links=links
    ) == (None, None)


@pytest.mark.parametrize("guid", ["OtherCode", "123456", "https://www.threads.com/t/OtherCode"])
def test_weak_guid_does_not_override_the_root_permalink(guid):
    configuration = config()
    material = parse_feed(feed(guid=guid), configuration.feed_url, configuration)[0]
    assert material.external_id is None
    assert material.native_identity.native_id == "AbC_012-"


def test_proof_and_configuration_tampering_are_rechecked_even_for_typed_copies():
    configuration = config()
    material = parse_feed(feed(), configuration.feed_url, configuration)[0]
    proof = material.native_identity
    assert proof is not None
    for changes in (
        {"native_id": "OtherCode"},
        {"canonical_object_url": "https://www.threads.com/t/OtherCode"},
        {"route_key": "/threads/other"},
        {"query_mode": "platform_keyword"},
        {"configuration_sha256": "f" * 64},
        {"collector_revision": "f" * 40},
        {"namespace": "instagram_shortcode"},
    ):
        forged = material.model_copy(update={"native_identity": proof.model_copy(update=changes)})
        assert verify_editorial_native_identity(forged, configuration=configuration) is None
    for changes in (
        {"external_id": "99999"},
        {"url": "https://www.threads.com/t/OtherCode"},
        {"identity_key": "feed-guid"},
        {"metadata": {"collector": "external"}},
    ):
        assert (
            verify_editorial_native_identity(
                material.model_copy(update=changes), configuration=configuration
            )
            is None
        )
    other_configuration = config(cache_ttl_seconds=600)
    assert verify_editorial_native_identity(material, configuration=other_configuration) is None
    with pytest.raises(ValidationError):
        EditorialNativeIdentityProof.model_validate(
            {**proof.model_dump(), "native_id": "OtherCode"}
        )


def test_atom_and_blocked_instagram_remain_without_production_native_proof():
    configuration = config()
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title><id>feed</id>'
        "<entry><title>Post</title><id>opaque</id>"
        '<link href="https://www.threads.com/t/AbC_012-"/>'
        '<author><name>sample</name></author><content type="html">'
        "&lt;p&gt;&lt;strong&gt;@sample&lt;/strong&gt;:&lt;/p&gt;</content></entry></feed>"
    )
    material = parse_feed(atom, configuration.feed_url, configuration)[0]
    assert material.native_identity is None and material.external_id is None
    instagram = config(
        platform="instagram",
        route="/instagram/2/user/sample",
        item_hosts=["www.instagram.com"],
        downstream_hosts=["www.instagram.com"],
        text_scope="caption",
    )
    material = parse_feed(
        feed(url="https://www.instagram.com/p/AbC_012-/"), instagram.feed_url, instagram
    )[0]
    assert material.native_identity is None and material.external_id is None


def test_normal_public_rss_keeps_feed_scoped_guid_identity():
    configuration = EditorialSourceConfiguration(
        kind="rss", feed_url="https://example.com/feed", allowed_hosts=("example.com",)
    )
    material = parse_feed(
        feed(url="https://example.com/post"), configuration.feed_url, configuration
    )[0]
    assert material.external_id == "weak-feed-guid" and material.native_identity is None


@pytest.mark.parametrize("representation", ["typed", "dict", "metadata", "case_variation"])
def test_external_ingress_rejects_native_proof_before_job_admission(representation):
    configuration = config()
    material = parse_feed(feed(), configuration.feed_url, configuration)[0]
    value = material if representation == "typed" else material.model_dump(mode="json")
    if representation in {"metadata", "case_variation"}:
        value["native_identity"] = None
        key = "native_identity" if representation == "metadata" else "Identity-Proof"
        value["metadata"] = {key: material.native_identity.model_dump(mode="json")}
    with pytest.raises(ValidationError, match="cannot declare server-native identity"):
        ExternalEditorialInput(
            operation_id=uuid4(), expected_revision=1, configuration_version=1, materials=(value,)
        )
    materials, receipts = prepare_external_materials((value,))
    assert materials == () and receipts[0].status == "rejected"


def test_external_material_with_no_native_claim_still_works():
    configuration = EditorialSourceConfiguration(
        kind="rss", feed_url="https://example.com/feed", allowed_hosts=("example.com",)
    )
    material = parse_feed(
        feed(url="https://example.com/post"), configuration.feed_url, configuration
    )[0]
    command = ExternalEditorialInput(
        operation_id=uuid4(),
        expected_revision=1,
        configuration_version=1,
        materials=(material.model_dump(mode="json"),),
    )
    materials, receipts = prepare_external_materials(command.materials)
    assert materials == (material,) and receipts[0].status == "pending"


@pytest.mark.parametrize(
    "encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"]
)
def test_non_utf8_encoding_with_or_without_dtd_never_produces_strong_proof(encoding):
    configuration = config()
    url = "https://www.threads.com/t/AbC_012-"
    for text in (feed(), '<!DOCTYPE rss [<!ENTITY post "injected">]>' + feed()):
        assert rsshub_native_identity_proofs(
            text.encode(encoding), configuration=configuration, parsed_links=(url,)
        ) == (None,)


@pytest.mark.parametrize(
    "prefix",
    [
        "<!DOCTYPE rss>",
        '<!DOCTYPE rss [<!ENTITY post "injected">]>',
        '<?xml version="1.0" encoding="ISO-8859-1"?>',
    ],
)
def test_dtd_entities_and_other_declared_encoding_never_produce_strong_proof(prefix):
    configuration = config()
    assert rsshub_native_identity_proofs(
        prefix + feed(),
        configuration=configuration,
        parsed_links=("https://www.threads.com/t/AbC_012-",),
    ) == (None,)


def test_external_claim_inspection_is_iterative_bounded_and_fails_closed():
    nested = {}
    for _ in range(2000):
        nested = {"child": nested}
    with pytest.raises(ValueError, match="inspection bound"):
        external_native_identity_claim(nested)
    with pytest.raises(ValueError, match="inspection bound"):
        external_native_identity_claim({str(index): index for index in range(10_001)})
    cyclic = {}
    cyclic["child"] = cyclic
    with pytest.raises(ValueError, match="inspection bound"):
        external_native_identity_claim(cyclic)
    configuration = config()
    material = parse_feed(feed(), configuration.feed_url, configuration)[0].model_copy(
        update={"native_identity": None, "metadata": nested}
    )
    with pytest.raises(ValidationError, match="inspection bound"):
        ExternalEditorialInput(
            operation_id=uuid4(),
            expected_revision=1,
            configuration_version=1,
            materials=(material,),
        )
