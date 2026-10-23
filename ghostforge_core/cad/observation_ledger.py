"""Batch ledger for completed CAD live-probe observations.

The observation-record module validates one capture.  This module loads all
captured records from a knowledge-base folder, validates them as a batch, and
summarizes which facts can safely feed Ghost Forge native CAD development.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .observation_records import (
    CadLiveProbeObservationRecord,
    CadObservationValidationReport,
    validate_cad_observation_record,
)
from .plasticity_recon import DEFAULT_PLASTICITY_KB_ROOT


OBSERVATION_LEDGER_FILENAMES = (
    "cad_live_observation_records.json",
    "cad_observation_records.json",
    "plasticity_live_observation_records.json",
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CadObservationLedgerEntry(FrozenModel):
    entry_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    source_file: str = ""
    source_index: int = 0
    record: CadLiveProbeObservationRecord
    validation: CadObservationValidationReport

    @property
    def accepted(self) -> bool:
        return self.validation.status in {
            "accepted_for_promotion",
            "accepted_for_partial",
            "accepted_for_static_owner",
        }


@dataclass(frozen=True)
class CadObservationLedgerCatalog:
    entries: tuple[CadObservationLedgerEntry, ...]
    kb_root: str
    source_files: tuple[str, ...] = ()

    def all_entries(self) -> list[CadObservationLedgerEntry]:
        return sorted(self.entries, key=lambda entry: (entry.command_id, entry.source_index, entry.entry_id))

    def entries_for_command(self, command_id: str) -> list[CadObservationLedgerEntry]:
        return [entry for entry in self.all_entries() if entry.command_id == command_id]

    def latest_for_command(self, command_id: str) -> CadObservationLedgerEntry:
        entries = self.entries_for_command(command_id)
        if not entries:
            raise KeyError(command_id)
        return entries[-1]

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        target_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        accepted = 0
        rejected = 0
        for entry in self.entries:
            status_counts[entry.validation.status] = status_counts.get(entry.validation.status, 0) + 1
            if entry.accepted:
                accepted += 1
            else:
                rejected += 1
            for target in entry.validation.promotion_targets:
                target_counts[target] = target_counts.get(target, 0) + 1
            for blocker in entry.validation.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "record_count": len(self.entries),
            "command_count": len({entry.command_id for entry in self.entries}),
            "accepted_count": accepted,
            "rejected_count": rejected,
            "status_counts": dict(sorted(status_counts.items())),
            "promotion_target_counts": dict(sorted(target_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "source_files": list(self.source_files),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def load_cad_observation_ledger(kb_root: str | Path | None = None) -> CadObservationLedgerCatalog:
    root = Path(kb_root) if kb_root else Path(DEFAULT_PLASTICITY_KB_ROOT)
    source_files = _source_files(root)
    entries: list[CadObservationLedgerEntry] = []
    for source_file in source_files:
        for index, payload in enumerate(_records_from_file(source_file), start=1):
            record = CadLiveProbeObservationRecord.model_validate(payload)
            validation = validate_cad_observation_record(record, root)
            entries.append(
                CadObservationLedgerEntry(
                    entry_id=f"{record.command_id}:{index}",
                    command_id=record.command_id,
                    source_file=str(source_file),
                    source_index=index,
                    record=record,
                    validation=validation,
                )
            )
    return CadObservationLedgerCatalog(
        entries=tuple(entries),
        kb_root=str(root),
        source_files=tuple(str(path) for path in source_files),
    )


def _source_files(root: Path) -> list[Path]:
    candidates = [root / filename for filename in OBSERVATION_LEDGER_FILENAMES]
    observations_dir = root / "observations"
    candidates.extend(observations_dir / filename for filename in OBSERVATION_LEDGER_FILENAMES)
    return [path for path in candidates if path.exists()]


def _records_from_file(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    if isinstance(payload, dict):
        for key in ("records", "observations", "entries"):
            value = payload.get(key)
            if isinstance(value, list):
                return [
                    item.get("record", item) if isinstance(item, dict) else item
                    for item in value
                    if isinstance(item, dict)
                ]
    return []


__all__ = [
    "CadObservationLedgerCatalog",
    "CadObservationLedgerEntry",
    "OBSERVATION_LEDGER_FILENAMES",
    "load_cad_observation_ledger",
]
