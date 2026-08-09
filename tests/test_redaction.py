from __future__ import annotations

import json
from urllib.parse import quote, unquote

from uptime_kuma_mcp.redaction import (
    REDACTED,
    redact,
    redact_text,
    safe_heartbeat,
    safe_monitor,
    safe_notification,
)


def test_recursive_redaction_covers_keys_headers_tokens_and_urls() -> None:
    value = {
        "password": "hunter2",
        "nested": {
            "apiKey": "abc",
            "message": "Authorization: Bearer abc.def.ghi",
            "url": "https://user:pass@example.test/path?token=abc&view=full",
        },
        "headers": {"Authorization": "Basic abc"},
    }
    serialized = json.dumps(redact(value))
    assert "hunter2" not in serialized
    assert "abc.def.ghi" not in serialized
    assert "user:pass" not in serialized
    assert '"token=abc"' not in serialized
    assert serialized.count(REDACTED) >= 4


def test_embedded_url_credentials_and_known_secret_paths_are_redacted() -> None:
    cases = {
        "failed https://user:pass@example.test/x?token=abc": ("user:pass", "token=abc"),
        "oauth https://example.test/x?access_token=OAUTHSECRET": ("OAUTHSECRET",),
        "signed https://example.test/x?signature=SIGNATURESECRET": ("SIGNATURESECRET",),
        "push https://status.example/api/push/SUPERSECRETPUSHTOKEN?status=up": (
            "SUPERSECRETPUSHTOKEN",
        ),
        "slack https://hooks.slack.com/services/T000/B000/VERYSECRET": ("VERYSECRET",),
        "discord https://discord.com/api/webhooks/123/WEBHOOKSECRET": ("WEBHOOKSECRET",),
    }

    for message, secrets in cases.items():
        result = redact_text(message)
        assert REDACTED in unquote(result)
        assert all(secret not in result for secret in secrets)


def test_monitor_projection_drops_secret_bearing_fields() -> None:
    result = safe_monitor(
        {
            "id": 1,
            "name": "API",
            "url": "https://example.test/health?api_key=secret",
            "headers": '{"Authorization":"Bearer secret"}',
            "basic_auth_pass": "secret",
            "databaseConnectionString": "postgres://u:p@example/db",
        }
    )
    assert result["id"] == 1
    assert "secret" not in result["url"]
    assert REDACTED in result["url"]
    assert "headers" not in result
    assert "basic_auth_pass" not in result
    assert "databaseConnectionString" not in result


def test_monitor_projection_redacts_normalized_query_keys_and_query_fragments() -> None:
    query_result = safe_monitor(
        {"url": "https://example.test/callback?client-secret=TOPSECRET&view=full"}
    )
    fragment_result = safe_monitor(
        {"url": "https://example.test/callback#access_token=TOPSECRET&view=full"}
    )

    assert "TOPSECRET" not in query_result["url"]
    assert f"client-secret={REDACTED}" in unquote(query_result["url"])
    assert "view=full" in query_result["url"]
    assert "TOPSECRET" not in fragment_result["url"]
    assert f"access_token={REDACTED}" in unquote(fragment_result["url"])
    assert "view=full" in fragment_result["url"]


def test_monitor_projection_fails_closed_for_malformed_url_ports() -> None:
    result = safe_monitor({"url": "https://alice:PORTSECRET@example.test:bad/path"})

    assert result["url"] == REDACTED
    assert "PORTSECRET" not in result["url"]


def test_monitor_projection_recursively_redacts_query_values() -> None:
    nested_url = safe_monitor(
        {
            "url": (
                "https://example.test/callback?"
                "redirect=https%3A%2F%2Ftarget.test%2Fx%3Faccess_token%3DNESTEDSECRET"
                "&view=full"
            )
        }
    )
    nested_assignment = safe_monitor(
        {"url": "https://example.test/callback?next=client-secret%3DASSIGNSECRET&view=full"}
    )

    assert "NESTEDSECRET" not in nested_url["url"]
    assert REDACTED in unquote(unquote(nested_url["url"]))
    assert "view=full" in nested_url["url"]
    assert "ASSIGNSECRET" not in nested_assignment["url"]
    assert REDACTED in unquote(nested_assignment["url"])
    assert "view=full" in nested_assignment["url"]


def test_monitor_projection_bounds_recursive_url_redaction() -> None:
    nested = "https://target.test/x?access_token=DEEPESTSECRET"
    for _ in range(5):
        nested = f"https://relay.test/callback?redirect={quote(nested, safe='')}"

    result = safe_monitor({"url": nested})

    assert "DEEPESTSECRET" not in result["url"]
    assert REDACTED in unquote(unquote(unquote(result["url"])))


def test_monitor_projection_redacts_multiply_encoded_query_values() -> None:
    double_url = safe_monitor(
        {
            "url": (
                "https://example.test/callback?next="
                "https%253A%252F%252Ftarget.test%252Fx%253Faccess_token%253DDOUBLESECRET"
                "&view=full"
            )
        }
    )
    triple_assignment = safe_monitor(
        {"url": ("https://example.test/callback?next=client-secret%25253DTRIPLESECRET&view=full")}
    )

    assert "DOUBLESECRET" not in double_url["url"]
    assert REDACTED in unquote(unquote(double_url["url"]))
    assert "view=full" in double_url["url"]
    assert "TRIPLESECRET" not in triple_assignment["url"]
    assert REDACTED in unquote(unquote(unquote(triple_assignment["url"])))
    assert "view=full" in triple_assignment["url"]


def test_normalized_assignments_are_redacted_in_text_and_heartbeats() -> None:
    names = (
        "access_token",
        "client_secret",
        "refresh_token",
        "proxy_password",
        "basic_auth_pass",
    )

    for name in names:
        message = f"callback failed: {name}=TEXTSECRET"
        heartbeat = safe_heartbeat({"id": 1, "msg": f"upstream error: {name}: HEARTBEATSECRET"})

        assert "TEXTSECRET" not in redact_text(message)
        assert REDACTED in redact_text(message)
        assert "HEARTBEATSECRET" not in heartbeat["msg"]
        assert REDACTED in heartbeat["msg"]


def test_quoted_assignments_are_redacted_in_text_and_heartbeats() -> None:
    cases = (
        ('{"access_token":"JSONTOKEN", "state":"ready"}', "JSONTOKEN", '"state":"ready"'),
        ("{'client_secret':'PYSECRET', 'state':'ready'}", "PYSECRET", "'state':'ready'"),
        ('{"access_token":"ALPHA BETA", "state":"ready"}', "ALPHA BETA", '"state":"ready"'),
        (
            '{"access_token":"ALPHA\\"OMEGA", "state":"ready"}',
            "ALPHA",
            '"state":"ready"',
        ),
    )

    for message, secret, neighbor in cases:
        text_result = redact_text(message)
        heartbeat_result = safe_heartbeat({"id": 1, "msg": message})

        assert secret not in text_result
        assert REDACTED in text_result
        assert neighbor in text_result
        assert secret not in heartbeat_result["msg"]
        assert REDACTED in heartbeat_result["msg"]
        assert neighbor in heartbeat_result["msg"]


def test_compound_sensitive_keys_are_redacted_in_mappings_text_and_heartbeats() -> None:
    cases = (
        "AWS_SECRET_ACCESS_KEY",
        "privateKeyPem",
        "authorizationHeader",
        "authKey",
        "authenticationKey",
        "clientCredentials",
    )

    for key in cases:
        mapping = redact({key: "MAPPINGSECRET", "state": "ready"})
        message = f"{key}=TEXTSECRET state=ready"
        heartbeat = safe_heartbeat({"id": 1, "msg": f"{key}: HEARTBEATSECRET state=ready"})

        assert mapping == {key: REDACTED, "state": "ready"}
        assert "TEXTSECRET" not in redact_text(message)
        assert "state=ready" in redact_text(message)
        assert "HEARTBEATSECRET" not in heartbeat["msg"]
        assert "state=ready" in heartbeat["msg"]


def test_authorization_headers_are_redacted_through_line_boundary() -> None:
    cases = (
        "Authorization: ApiKey SUPERSECRET",
        ('Authorization: Digest username="admin", nonce="NONCESECRET", response="RESPONSESECRET"'),
        "Proxy-Authorization: Custom PROXYSECRET with trailing material",
    )

    for header in cases:
        message = f"upstream rejected request\n{header}\nstate=ready"
        text_result = redact_text(message)
        heartbeat_result = safe_heartbeat({"id": 1, "msg": message})

        assert text_result.endswith("\nstate=ready")
        assert heartbeat_result["msg"].endswith("\nstate=ready")
        assert REDACTED in text_result
        assert REDACTED in heartbeat_result["msg"]
        for secret in ("SUPERSECRET", "NONCESECRET", "RESPONSESECRET", "PROXYSECRET"):
            assert secret not in text_result
            assert secret not in heartbeat_result["msg"]


def test_sensitive_key_classifier_preserves_benign_near_matches() -> None:
    values = {
        "author": "Ada",
        "keyboard": "qwerty",
        "monkey": "banana",
        "passwordless": True,
        "secretary": "Grace",
        "tokenizer": "wordpiece",
    }

    assert redact(values) == values
    for key, value in values.items():
        assert redact_text(f"{key}={value}") == f"{key}={value}"


def test_monitor_projection_redacts_encoded_fragments() -> None:
    assignment = safe_monitor(
        {"url": "https://example.test/callback#access_token%3DFRAGMENTSECRET"}
    )
    double_assignment = safe_monitor(
        {"url": "https://example.test/callback#client_secret%253DDOUBLEFRAGMENTSECRET"}
    )
    nested_url = safe_monitor(
        {
            "url": (
                "https://example.test/callback#"
                "https%253A%252F%252Ftarget.test%252Fx%253Faccess_token%253DNESTEDFRAGMENTSECRET"
            )
        }
    )

    assert "FRAGMENTSECRET" not in assignment["url"]
    assert REDACTED in unquote(assignment["url"])
    assert "DOUBLEFRAGMENTSECRET" not in double_assignment["url"]
    assert REDACTED in unquote(unquote(double_assignment["url"]))
    assert "NESTEDFRAGMENTSECRET" not in nested_url["url"]
    assert REDACTED in unquote(unquote(nested_url["url"]))


def test_notification_projection_never_returns_provider_configuration() -> None:
    result = safe_notification(
        {
            "id": 3,
            "name": "Slack",
            "active": True,
            "config": json.dumps({"type": "slack", "webhookURL": "https://hooks/secret"}),
        }
    )
    assert result == {
        "id": 3,
        "name": "Slack",
        "type": "slack",
        "active": True,
        "isDefault": False,
    }
