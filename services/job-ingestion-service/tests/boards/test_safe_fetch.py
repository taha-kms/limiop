"""Refusing a URL that would leave the public internet.

Table-driven: one row per rule `is_public_http_url` enforces, each paired
with the resolver it needs to prove the point. None of this touches real
DNS — every row supplies its own resolver.
"""

from collections.abc import Callable

import pytest

from job_ingestion.boards.safe_fetch import is_public_http_url


def resolver_returning(*addresses: str) -> Callable[[str], list[str]]:
    return lambda _hostname: list(addresses)


def failing_resolver(_hostname: str) -> list[str]:
    raise OSError("name resolution failed")


CASES: tuple[tuple[str, str, Callable[[str], list[str]], bool], ...] = (
    (
        "a public https url with a public resolver",
        "https://example.com",
        resolver_returning("93.184.216.34"),
        True,
    ),
    ("a non-http(s) scheme", "ftp://example.com/", resolver_returning("93.184.216.34"), False),
    (
        "an ip literal, even a link-local one",
        "http://169.254.169.254/latest/meta-data/",
        resolver_returning("169.254.169.254"),
        False,
    ),
    ("localhost by name", "http://localhost/", resolver_returning("127.0.0.1"), False),
    ("userinfo in the url", "http://user@example.com/", resolver_returning("93.184.216.34"), False),
    ("a non-standard port", "http://example.com:8080/", resolver_returning("93.184.216.34"), False),
    (
        "a hostname that resolves to a private address",
        "http://internal.example.com/",
        resolver_returning("10.0.0.5"),
        False,
    ),
    (
        "a hostname resolving to both a public and a private address",
        "http://mixed.example.com/",
        resolver_returning("93.184.216.34", "10.0.0.5"),
        False,
    ),
    ("a resolver that fails", "http://unresolvable.example.com/", failing_resolver, False),
    (
        "a shared address space (CGNAT) address",
        "http://cgnat.example.com/",
        resolver_returning("100.64.0.1"),
        False,
    ),
)


@pytest.mark.parametrize("description,url,resolve,expected", CASES, ids=[case[0] for case in CASES])
def test_is_public_http_url(
    description: str, url: str, resolve: Callable[[str], list[str]], expected: bool
) -> None:
    assert is_public_http_url(url, resolve=resolve) is expected, description


def test_a_local_suffix_hostname_is_refused() -> None:
    assert (
        is_public_http_url("http://board.internal/", resolve=resolver_returning("93.184.216.34"))
        is False
    )
    assert (
        is_public_http_url("http://board.local/", resolve=resolver_returning("93.184.216.34"))
        is False
    )


def test_no_hostname_at_all_is_refused() -> None:
    assert is_public_http_url("http:///path", resolve=resolver_returning("93.184.216.34")) is False


def test_a_loopback_address_from_the_resolver_is_refused() -> None:
    assert (
        is_public_http_url("http://rebinder.example.com/", resolve=resolver_returning("127.0.0.1"))
        is False
    )


def test_an_ipv6_loopback_literal_is_refused() -> None:
    assert is_public_http_url("http://[::1]/", resolve=resolver_returning("::1")) is False


def test_a_resolver_returning_no_addresses_is_refused() -> None:
    assert is_public_http_url("http://empty.example.com/", resolve=lambda _hostname: []) is False


def test_an_unparseable_resolved_address_is_refused() -> None:
    assert (
        is_public_http_url("http://garbage.example.com/", resolve=resolver_returning("not-an-ip"))
        is False
    )
