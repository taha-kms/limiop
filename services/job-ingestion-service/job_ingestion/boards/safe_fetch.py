"""Refusing to fetch a URL that would leave the public internet.

Verification (`pinpoint/verification.py`) reaches URLs built from untrusted
input — a company's stated website, read from a posting payload or Wikidata,
and every redirect target that website's own pages point at. Nothing here
trusts any of it: a payload naming `http://169.254.169.254/latest/meta-data/`,
or a page that redirects to `http://127.0.0.1:5432/` or `http://10.0.0.5/`,
would otherwise be fetched by the ingestion worker from inside its own
deployment network. This is the one gate every such fetch passes through
first.

Checking the literal host in the URL is not enough on its own — DNS answers
what it likes, and a hostname that looks public can still resolve to
something that is not. So this resolves the hostname and inspects every
address it comes back with, not only the URL's own text.
"""

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_ALLOWED_PORTS = frozenset({80, 443})
_LOCAL_HOSTNAMES = frozenset({"localhost"})
_LOCAL_SUFFIXES = (".local", ".internal", ".localhost")
# Shared address space (RFC 6598), used by carrier-grade NAT: internal-only in
# practice, but `ipaddress.IPv4Address.is_private` does not flag it.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


def default_resolver(hostname: str) -> list[str]:
    """Every address `hostname` resolves to. Raises `OSError` on failure,
    exactly as `socket.getaddrinfo` does — callers decide what that means."""
    infos = socket.getaddrinfo(hostname, None)
    return [str(info[4][0]) for info in infos]


def _is_unsafe_address(text: str) -> bool:
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        # Not an address `ipaddress` can parse at all: refuse rather than
        # guess at what the resolver meant.
        return True
    if isinstance(address, ipaddress.IPv4Address) and address in _SHARED_ADDRESS_SPACE:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def is_public_http_url(url: str, *, resolve: Callable[[str], list[str]] = default_resolver) -> bool:
    """Whether `url` names a plain HTTP(S) address that resolves only to the
    public internet.

    Every rule refuses rather than allows on doubt: an unparseable URL, a
    hostname that fails to resolve, or a hostname that resolves to even one
    unsafe address alongside a public one, is not a public URL as far as
    this is concerned. A literal IP in the URL is refused outright, public
    or not — verification only ever expects a hostname there, and an IP
    literal is exactly how a check that resolved hostnames but trusted a
    literal address would be bypassed.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if parsed.port is not None and parsed.port not in _ALLOWED_PORTS:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname in _LOCAL_HOSTNAMES or hostname.endswith(_LOCAL_SUFFIXES):
        return False
    if _is_ip_literal(hostname):
        return False

    try:
        addresses = resolve(hostname)
    except OSError:
        return False
    if not addresses:
        return False
    return not any(_is_unsafe_address(address) for address in addresses)
