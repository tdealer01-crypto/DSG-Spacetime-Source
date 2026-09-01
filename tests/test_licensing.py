import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization

from dsg_spacetime.licensing import (
    generate_signing_key,
    issue_entitlement,
    issue_entitlement_from_private_key_b64,
    public_key_b64_from_private_key_b64,
)
from dsg_spacetime.runtime import LicenseVerifier


def test_seller_can_issue_offline_route_license(tmp_path):
    key_path = tmp_path / "seller-ed25519.pem"
    public_key_b64 = generate_signing_key(str(key_path))
    assert key_path.exists()
    assert len(base64.b64decode(public_key_b64)) == 32

    now = datetime.now(timezone.utc)
    entitlement = issue_entitlement(
        private_key_path=str(key_path),
        entitlement_id="ent-market-1",
        customer_id="customer-a",
        deployment_id="deployment-a",
        allowed_routes=["route.ai-github.write", "route.ai-github.write"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=365),
    )
    assert entitlement.allowed_routes == ("route.ai-github.write",)
    assert entitlement.route_limit is None

    verifier = LicenseVerifier(public_key_b64)
    verifier.verify(entitlement, deployment_id="deployment-a", now=now)


def test_entitlement_is_bound_to_customer_deployment(tmp_path):
    key_path = tmp_path / "seller-ed25519.pem"
    public_key_b64 = generate_signing_key(str(key_path))
    now = datetime.now(timezone.utc)
    entitlement = issue_entitlement(
        private_key_path=str(key_path),
        entitlement_id="ent-market-2",
        customer_id="customer-a",
        deployment_id="deployment-a",
        allowed_routes=["route.ai-github.write"],
        not_before=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=30),
    )
    verifier = LicenseVerifier(public_key_b64)
    with pytest.raises(PermissionError, match="ENTITLEMENT_DEPLOYMENT_MISMATCH"):
        verifier.verify(entitlement, deployment_id="deployment-b", now=now)


def test_capacity_entitlement_can_be_perpetual_and_verified_from_secret_material(tmp_path):
    key_path = tmp_path / "seller-ed25519.pem"
    generate_signing_key(str(key_path))
    key_b64 = base64.b64encode(key_path.read_bytes()).decode("ascii")
    public_key_b64 = public_key_b64_from_private_key_b64(key_b64)
    assert len(base64.b64decode(public_key_b64)) == 32

    now = datetime.now(timezone.utc)
    entitlement = issue_entitlement_from_private_key_b64(
        private_key_b64=key_b64,
        entitlement_id="ent-capacity-5",
        customer_id="cus_123",
        deployment_id="dsg-deploy-123",
        route_limit=5,
        not_before=now - timedelta(minutes=1),
        expires_at=None,
    )
    assert entitlement.allowed_routes == ()
    assert entitlement.route_limit == 5
    assert entitlement.expires_at is None
    LicenseVerifier(public_key_b64).verify(
        entitlement,
        deployment_id="dsg-deploy-123",
        now=now,
    )


def test_entitlement_scope_cannot_mix_allowlist_and_capacity(tmp_path):
    key_path = tmp_path / "seller-ed25519.pem"
    generate_signing_key(str(key_path))
    key_b64 = base64.b64encode(key_path.read_bytes()).decode("ascii")
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="ENTITLEMENT_SCOPE_INVALID"):
        issue_entitlement_from_private_key_b64(
            private_key_b64=key_b64,
            entitlement_id="ent-invalid",
            customer_id="cus_123",
            deployment_id="dsg-deploy-123",
            allowed_routes=["route.a"],
            route_limit=5,
            not_before=now - timedelta(minutes=1),
            expires_at=None,
        )
