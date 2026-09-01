from __future__ import annotations

import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .runtime import Entitlement, _canonical


def _public_key_b64(private_key: Ed25519PrivateKey) -> str:
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_raw).decode("ascii")


def generate_signing_key(private_key_path: str) -> str:
    """Create a seller-side Ed25519 key and return the public key in base64.

    The private key is written only to the caller-selected local path with mode 0600.
    It must never be committed to the repository.
    """
    path = Path(private_key_path)
    if path.exists():
        raise FileExistsError("LICENSE_SIGNING_KEY_ALREADY_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, pem)
    finally:
        os.close(fd)

    return _public_key_b64(private_key)


def _parse_private_key(raw: bytes) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("LICENSE_SIGNING_KEY_TYPE_INVALID")
    return key


def _load_private_key(path: str) -> Ed25519PrivateKey:
    return _parse_private_key(Path(path).read_bytes())


def load_private_key_b64(value: str) -> Ed25519PrivateKey:
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError("LICENSE_SIGNING_KEY_B64_INVALID") from exc
    return _parse_private_key(raw)


def public_key_b64_from_private_key_b64(value: str) -> str:
    return _public_key_b64(load_private_key_b64(value))


def _issue_entitlement(
    *,
    private_key: Ed25519PrivateKey,
    entitlement_id: str,
    customer_id: str,
    deployment_id: str,
    allowed_routes: Iterable[str],
    route_limit: int | None,
    not_before: datetime,
    expires_at: datetime | None,
) -> Entitlement:
    if not_before.tzinfo is None or (expires_at is not None and expires_at.tzinfo is None):
        raise ValueError("ENTITLEMENT_TIMEZONE_REQUIRED")
    if expires_at is not None and expires_at <= not_before:
        raise ValueError("ENTITLEMENT_TIME_RANGE_INVALID")
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise ValueError("ENTITLEMENT_ALREADY_EXPIRED")

    routes = tuple(sorted(set(allowed_routes)))
    if bool(routes) == (route_limit is not None):
        raise ValueError("ENTITLEMENT_SCOPE_INVALID")
    if route_limit is not None and not (1 <= route_limit <= 100_000):
        raise ValueError("ENTITLEMENT_ROUTE_LIMIT_INVALID")

    unsigned = Entitlement(
        entitlement_id=entitlement_id,
        customer_id=customer_id,
        deployment_id=deployment_id,
        allowed_routes=routes,
        route_limit=route_limit,
        not_before=not_before,
        expires_at=expires_at,
        signature_b64="",
    )
    signature = private_key.sign(_canonical(unsigned.unsigned_payload()))
    return unsigned.model_copy(
        update={"signature_b64": base64.b64encode(signature).decode("ascii")}
    )


def issue_entitlement(
    *,
    private_key_path: str,
    entitlement_id: str,
    customer_id: str,
    deployment_id: str,
    allowed_routes: Iterable[str] = (),
    route_limit: int | None = None,
    not_before: datetime,
    expires_at: datetime | None,
) -> Entitlement:
    return _issue_entitlement(
        private_key=_load_private_key(private_key_path),
        entitlement_id=entitlement_id,
        customer_id=customer_id,
        deployment_id=deployment_id,
        allowed_routes=allowed_routes,
        route_limit=route_limit,
        not_before=not_before,
        expires_at=expires_at,
    )


def issue_entitlement_from_private_key_b64(
    *,
    private_key_b64: str,
    entitlement_id: str,
    customer_id: str,
    deployment_id: str,
    allowed_routes: Iterable[str] = (),
    route_limit: int | None = None,
    not_before: datetime,
    expires_at: datetime | None,
) -> Entitlement:
    return _issue_entitlement(
        private_key=load_private_key_b64(private_key_b64),
        entitlement_id=entitlement_id,
        customer_id=customer_id,
        deployment_id=deployment_id,
        allowed_routes=allowed_routes,
        route_limit=route_limit,
        not_before=not_before,
        expires_at=expires_at,
    )
