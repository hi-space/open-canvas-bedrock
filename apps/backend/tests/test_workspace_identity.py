"""Real ES256 signature checks with only the AWS key download replaced."""
import hashlib
import os
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
import jwt
from starlette.requests import Request

from api.workspaces.identity import owner_key

SIGNER = "arn:aws:elasticloadbalancing:ap-northeast-2:123456789012:loadbalancer/app/canvas/abcd"


class WorkspaceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        self.environment = patch.dict(os.environ, {
            "WORKSPACE_AUTH_MODE": "alb", "ALB_SIGNER_ARN": SIGNER, "COGNITO_CLIENT_ID": "client",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def token(self, **headers):
        return jwt.encode({"sub": "verified-user"}, self.private_key, algorithm="ES256", headers={
            "kid": "00000000-0000-0000-0000-000000000000", "signer": SIGNER,
            "client": "client", "exp": int(time.time()) + 300, **headers,
        })

    def request(self, token):
        return Request({"type": "http", "headers": [
            (b"x-amzn-oidc-data", token.encode()), (b"x-workspace-owner", b"attacker"),
        ]})

    def test_verified_subject_is_hashed_and_caller_owner_header_has_no_authority(self):
        with patch("api.workspaces.identity.public_key", return_value=self.public_key):
            owner = owner_key(self.request(self.token()))
        self.assertEqual(owner, hashlib.sha256(b"verified-user").hexdigest())

    def test_expired_wrong_signer_wrong_client_and_path_kids_fail(self):
        for headers in [
            {"exp": int(time.time()) - 1}, {"signer": SIGNER + "other"},
            {"client": "other"}, {"kid": "../../metadata"},
        ]:
            with self.subTest(headers=headers), patch("api.workspaces.identity.public_key", return_value=self.public_key):
                with self.assertRaises(HTTPException) as caught:
                    owner_key(self.request(self.token(**headers)))
                self.assertEqual(caught.exception.status_code, 401)

    def test_forged_signature_with_matching_claims_fails(self):
        other_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        with patch("api.workspaces.identity.public_key", return_value=other_key):
            with self.assertRaises(HTTPException) as caught:
                owner_key(self.request(self.token()))
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
