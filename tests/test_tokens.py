from __future__ import annotations

import jwt
import pytest

from uptime_kuma_mcp.tokens import issue_token


def test_issued_token_has_required_claims_and_scope() -> None:
    secret = "z" * 32
    token = issue_token(
        secret=secret,
        issuer="issuer",
        audience="audience",
        subject="pedro",
        ttl_seconds=3600,
        now=1_700_000_000,
    )
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="issuer",
        audience="audience",
        options={"verify_exp": False},
    )
    assert claims["sub"] == "pedro"
    assert claims["client_id"] == "pedro"
    assert claims["scope"] == "read:kuma"
    assert claims["exp"] - claims["iat"] == 3600


@pytest.mark.parametrize("ttl", [59, 31_536_001])
def test_token_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValueError, match="ttl_seconds"):
        issue_token(
            secret="z" * 32,
            issuer="issuer",
            audience="audience",
            subject="pedro",
            ttl_seconds=ttl,
        )
