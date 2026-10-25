"""Verify the ALB signature before deriving a project owner."""
import hashlib
import os
import re
import time
from functools import lru_cache

import httpx
from fastapi import HTTPException, Request


@lru_cache(maxsize=32)
def public_key(region: str, kid: str, hour: int) -> str:
    response = httpx.get(
        f"https://public-keys.auth.elb.{region}.amazonaws.com/{kid}",
        timeout=5, follow_redirects=False,
    )
    response.raise_for_status()
    if len(response.content) > 10000:
        raise ValueError("Invalid verification key")
    return response.text


def owner_key(request: Request) -> str:
    mode = os.environ.get("WORKSPACE_AUTH_MODE", "alb")
    if mode == "local":
        # Development must be explicitly opted into, never inferred from failure.
        if os.environ.get("ALB_SIGNER_ARN") or os.environ.get("COGNITO_DOMAIN"):
            raise HTTPException(503, "인증 환경 설정을 확인해 주세요.")
        subject = os.environ.get("WORKSPACE_LOCAL_SUB", "local-development")
        return hashlib.sha256(subject.encode()).hexdigest()
    if mode != "alb":
        raise HTTPException(503, "작업 공간 인증 설정을 확인해 주세요.")
    token = request.headers.get("x-amzn-oidc-data", "")
    if not token or len(token) > 20000:
        raise HTTPException(401, "로그인이 필요합니다.")
    try:
        import jwt

        header = jwt.get_unverified_header(token)
        signer = os.environ.get("ALB_SIGNER_ARN", "")
        region = signer.split(":")[3]
        kid = header.get("kid", "")
        client = os.environ.get("COGNITO_CLIENT_ID", "")
        if (
            not signer or header.get("signer") != signer or header.get("alg") != "ES256"
            or not re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", region)
            or not re.fullmatch(r"[a-fA-F0-9-]{36}", kid)
            or not client or header.get("client") != client
        ):
            raise ValueError("Wrong signing authority")
        key = public_key(region, kid, int(time.time() // 3600))
        claims = jwt.decode(
            token, key, algorithms=["ES256"],
            options={"verify_aud": False, "verify_exp": True},
        )
        # ALB puts expiry in the protected header, rather than only the payload.
        if float(header["exp"]) <= time.time():
            raise ValueError("Expired authentication")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 200:
            raise ValueError("Missing subject")
    except Exception:
        raise HTTPException(401, "로그인이 만료되었거나 확인되지 않았습니다. 다시 로그인해 주세요.") from None
    return hashlib.sha256(subject.encode()).hexdigest()
