from __future__ import annotations

import os
from pathlib import Path

from .runtime import EvidenceChain, EvidenceRecord, _hash


class JsonlEvidenceChain(EvidenceChain):
    """Customer-owned durable append-only evidence store."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records: list[EvidenceRecord] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(EvidenceRecord.model_validate_json(line))
        super().__init__(records=records)
        if not self.verify_chain():
            raise RuntimeError("EVIDENCE_CHAIN_INVALID_AT_STARTUP")

    def ensure_ready(self) -> None:
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def append(self, **kwargs) -> EvidenceRecord:  # type: ignore[override]
        record = super().append(**kwargs)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                data = (record.model_dump_json() + "\n").encode("utf-8")
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception:
            self.records.pop()
            raise
        return record

    def verify_chain(self) -> bool:
        previous: str | None = None
        for record in self.records:
            body = {
                "index": record.index,
                "timestamp": record.timestamp.isoformat(),
                "plan_id": record.plan_id,
                "route_id": record.route_id,
                "agent_id": record.agent_id,
                "decision_hash": record.decision_hash,
                "request_hash": record.request_hash,
                "result_hash": record.result_hash,
                "previous_hash": previous,
            }
            if record.previous_hash != previous or record.evidence_hash != _hash(body):
                return False
            previous = record.evidence_hash
        return True
