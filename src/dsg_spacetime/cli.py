from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .console import serve_console
from .licensing import generate_signing_key, issue_entitlement
from .mcp_stdio import serve_stdio


REQUIRED_PUBLIC_MANIFEST_KEYS = {
    "product",
    "model",
    "deployment",
    "commercial_unit",
    "public_surfaces",
}


def _validate_manifest(path: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_PUBLIC_MANIFEST_KEYS - payload.keys())
    if missing:
        raise SystemExit(f"manifest missing keys: {', '.join(missing)}")
    forbidden = {"source", "source_code", "algorithm", "secret", "solver_formula"}
    leaked = sorted(forbidden.intersection(payload.keys()))
    if leaked:
        raise SystemExit(f"public manifest contains forbidden fields: {', '.join(leaked)}")
    print("DSG Spacetime public manifest: PASS")
    return 0


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SystemExit("datetime must include timezone")
    return parsed


def _generate_key(path: str) -> int:
    public_key_b64 = generate_signing_key(path)
    print(public_key_b64)
    return 0


def _issue(args: argparse.Namespace) -> int:
    output = Path(args.output)
    if output.exists():
        raise SystemExit("output entitlement already exists")
    entitlement = issue_entitlement(
        private_key_path=args.key,
        entitlement_id=args.entitlement_id,
        customer_id=args.customer_id,
        deployment_id=args.deployment_id,
        allowed_routes=args.route,
        route_limit=args.route_limit,
        not_before=_parse_datetime(args.not_before),
        expires_at=_parse_datetime(args.expires_at) if args.expires_at else None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(entitlement.model_dump_json(indent=2), encoding="utf-8")
    print(str(output))
    return 0


def _add_runtime_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True)
    parser.add_argument("--entitlement", required=True)
    parser.add_argument("--evidence", required=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="dsg-spacetime")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-public-manifest")
    validate.add_argument("path")

    generate = sub.add_parser("generate-license-key")
    generate.add_argument("path", help="local path for seller private key; must not be committed")

    issue = sub.add_parser("issue-license")
    issue.add_argument("--key", required=True)
    issue.add_argument("--entitlement-id", required=True)
    issue.add_argument("--customer-id", required=True)
    issue.add_argument("--deployment-id", required=True)
    issue.add_argument("--route", action="append", default=[])
    issue.add_argument("--route-limit", type=int)
    issue.add_argument("--not-before", required=True)
    issue.add_argument("--expires-at")
    issue.add_argument("--output", required=True)

    serve = sub.add_parser("serve-mcp")
    _add_runtime_paths(serve)

    console = sub.add_parser("serve-console")
    _add_runtime_paths(console)
    console.add_argument("--host", default="127.0.0.1")
    console.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()
    if args.command == "validate-public-manifest":
        return _validate_manifest(args.path)
    if args.command == "generate-license-key":
        return _generate_key(args.path)
    if args.command == "issue-license":
        return _issue(args)
    if args.command == "serve-mcp":
        return serve_stdio(
            config_path=args.config,
            entitlement_path=args.entitlement,
            evidence_path=args.evidence,
        )
    if args.command == "serve-console":
        return serve_console(
            config_path=args.config,
            entitlement_path=args.entitlement,
            evidence_path=args.evidence,
            host=args.host,
            port=args.port,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
