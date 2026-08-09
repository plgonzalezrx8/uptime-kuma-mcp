"""Recursive redaction and explicit safe projections."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "authorization",
    "auth_header",
    "headers",
    "http_headers",
    "grpc_metadata",
    "password",
    "passphrase",
    "secret",
    "token",
    "api_key",
    "apikey",
    "push_token",
    "private_key",
    "basic_auth_pass",
    "mqtt_password",
    "radius_secret",
    "database_connection_string",
    "mongodb_url",
    "docker_daemon",
    "proxy_password",
    "client_cert",
    "certificate",
}
_SENSITIVE_SUFFIXES = ("_password", "_pass", "_secret", "_token", "_api_key", "_private_key")
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
}
_BEARER_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_AUTHORIZATION_HEADER_RE = re.compile(
    r"(?im)(?P<prefix>(?<![A-Za-z0-9_-])(?:proxy-)?authorization\s*:\s*)[^\r\n]*"
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)(?=(?P<assignment>(?<![A-Za-z0-9_-])"
    r"(?P<key_quote>['\"]?)(?P<key>[A-Za-z][A-Za-z0-9_-]*)"
    r"(?P=key_quote)\s*(?P<separator>[:=])\s*(?:"
    r'"(?P<double_value>(?:\\.|[^"\\])*)"'
    r"|'(?P<single_value>(?:\\.|[^'\\])*)'"
    r"|(?P<unquoted_value>[^\s,;&#}]+)"
    r")))"
)
_URL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>'\"]+")
_URL_TRAILING_PUNCTUATION = ".,;:!?)]}"
_MAX_URL_REDACTION_DEPTH = 3
_SECRET_PATH_PATTERNS = (
    re.compile(r"(?i)(/api/push/)[^/?#]+"),
    re.compile(r"(?i)(/api/webhooks/[^/?#]+/)[^/?#]+"),
    re.compile(r"(?i)(/services/[^/?#]+/[^/?#]+/)[^/?#]+"),
    re.compile(r"(?i)(/bot)[^/?#]+"),
)

_MONITOR_FIELDS = {
    "id",
    "name",
    "type",
    "active",
    "weight",
    "url",
    "hostname",
    "port",
    "interval",
    "retryInterval",
    "resendInterval",
    "maxretries",
    "timeout",
    "method",
    "bodyEncoding",
    "ignoreTls",
    "upsideDown",
    "expiryNotification",
    "accepted_statuscodes",
    "description",
    "dns_resolve_type",
    "dns_resolve_server",
    "packetSize",
    "buffer",
    "grpcUrl",
    "grpcServiceName",
    "grpcMethod",
    "grpcEnableTls",
    "notificationIDList",
    "tags",
    "parent",
    "childrenIDs",
}
_HEARTBEAT_FIELDS = {"id", "monitor_id", "status", "time", "msg", "ping", "duration", "important"}
_MAINTENANCE_FIELDS = {
    "id",
    "title",
    "description",
    "strategy",
    "active",
    "dateRange",
    "timeRange",
    "weekdays",
    "daysOfMonth",
    "intervalDay",
    "durationMinutes",
    "timezone",
}
_STATUS_PAGE_FIELDS = {
    "id",
    "title",
    "slug",
    "published",
    "showTags",
    "domainNameList",
    "createdDate",
    "modifiedDate",
}


def _normalize_key(key: object) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key)).lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalize_key(key)
    tokens = set(normalized.split("_"))
    sensitive_tokens = {
        "auth",
        "authentication",
        "authorization",
        "credential",
        "credentials",
        "password",
        "passwd",
        "passphrase",
        "secret",
        "token",
    }
    key_qualifiers = {
        "access",
        "api",
        "auth",
        "authentication",
        "authorization",
        "client",
        "credential",
        "credentials",
        "encryption",
        "private",
        "secret",
        "signing",
    }
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith(_SENSITIVE_SUFFIXES)
        or bool(tokens & sensitive_tokens)
        or ("key" in tokens and bool(tokens & key_qualifiers))
    )


def _is_sensitive_query_key(key: object) -> bool:
    normalized = _normalize_key(key)
    return normalized in _SENSITIVE_QUERY_KEYS or _is_sensitive_key(normalized)


def _redact_query_value(value: str, depth: int) -> str:
    decoded = unquote(value)
    if decoded != value:
        if depth >= _MAX_URL_REDACTION_DEPTH - 1:
            return REDACTED
        return _redact_query_value(decoded, depth + 1)
    return _redact_text(value, depth)


def _redact_query_values(value: str, depth: int) -> str:
    return urlencode(
        [
            (
                key,
                REDACTED if _is_sensitive_query_key(key) else _redact_query_value(item, depth + 1),
            )
            for key, item in parse_qsl(value, keep_blank_values=True)
        ],
        doseq=True,
    )


def _redact_fragment(value: str, depth: int) -> str:
    decoded = unquote(value)
    if decoded != value:
        if depth >= _MAX_URL_REDACTION_DEPTH - 1:
            return REDACTED
        return _redact_fragment(decoded, depth + 1)
    if "=" in value:
        return _redact_query_values(value, depth)
    return _redact_text(value, depth)


def _redact_url_match(match: re.Match[str], depth: int) -> str:
    raw_url = match.group(0)
    url = raw_url.rstrip(_URL_TRAILING_PUNCTUATION)
    suffix = raw_url[len(url) :]
    try:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            return raw_url
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        host = f"{hostname}:{parsed.port}" if parsed.port else hostname
        if parsed.username is not None or parsed.password is not None:
            host = f"{REDACTED}@{host}"
        path = parsed.path
        for pattern in _SECRET_PATH_PATTERNS:
            path = pattern.sub(lambda item: f"{item.group(1)}{REDACTED}", path)
        query = _redact_query_values(parsed.query, depth)
        fragment = _redact_fragment(parsed.fragment, depth)
        return urlunsplit((parsed.scheme, host, path, query, fragment)) + suffix
    except ValueError:
        return REDACTED + suffix


def _redact_text(value: str, depth: int) -> str:
    if depth >= _MAX_URL_REDACTION_DEPTH:
        redacted = _URL_RE.sub(REDACTED, value)
    else:
        redacted = _URL_RE.sub(lambda match: _redact_url_match(match, depth), value)
    redacted = _AUTHORIZATION_HEADER_RE.sub(
        lambda match: f"{match.group('prefix')}{REDACTED}", redacted
    )
    redacted = _BEARER_RE.sub(lambda match: f"{match.group(1)} {REDACTED}", redacted)
    redacted = _JWT_RE.sub(REDACTED, redacted)
    return _redact_assignments(redacted)


def _redacted_assignment(match: re.Match[str]) -> str:
    value_quote = '"' if match.group("double_value") is not None else "'"
    if match.group("unquoted_value") is not None:
        value_quote = ""
    return (
        f"{match.group('key_quote')}{match.group('key')}{match.group('key_quote')}"
        f"{match.group('separator')}{value_quote}{REDACTED}{value_quote}"
    )


def _redact_assignments(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _ASSIGNMENT_RE.finditer(value):
        if not _is_sensitive_query_key(match.group("key")):
            continue
        start, end = match.span("assignment")
        if start < cursor:
            continue
        parts.extend((value[cursor:start], _redacted_assignment(match)))
        cursor = end
    parts.append(value[cursor:])
    return "".join(parts)


def redact_text(value: str) -> str:
    """Redact common credentials from arbitrary text without logging the original."""
    return _redact_text(value, 0)


def redact(value: Any) -> Any:
    """Recursively redact secret-shaped keys and credential-shaped strings."""
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _is_sensitive_key(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact(item) for item in value]
    return value


def _project(source: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    return cast(dict[str, Any], redact({key: source[key] for key in allowed if key in source}))


def safe_monitor(source: Mapping[str, Any]) -> dict[str, Any]:
    return _project(source, _MONITOR_FIELDS)


def safe_heartbeat(source: Mapping[str, Any]) -> dict[str, Any]:
    return _project(source, _HEARTBEAT_FIELDS)


def safe_maintenance(source: Mapping[str, Any]) -> dict[str, Any]:
    return _project(source, _MAINTENANCE_FIELDS)


def safe_status_page(source: Mapping[str, Any]) -> dict[str, Any]:
    return _project(source, _STATUS_PAGE_FIELDS)


def safe_notification(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return notification identity/type only; provider configuration never leaves here."""
    provider_type: str | None = None
    config = source.get("config")
    if isinstance(config, str):
        try:
            decoded = json.loads(config)
        except (json.JSONDecodeError, TypeError):
            decoded = None
        if isinstance(decoded, Mapping) and isinstance(decoded.get("type"), str):
            provider_type = decoded["type"]
    elif isinstance(config, Mapping) and isinstance(config.get("type"), str):
        provider_type = config["type"]

    return cast(
        dict[str, Any],
        redact(
            {
                "id": source.get("id"),
                "name": source.get("name"),
                "type": provider_type,
                "active": bool(source.get("active", False)),
                "isDefault": bool(source.get("isDefault", False)),
            }
        ),
    )
