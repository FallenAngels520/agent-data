from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_data.domain.errors import ErrorCode, PipelineError
from agent_data.domain.models import AgentReadyPackage, ParsedDocument, ResolvedSource


@dataclass(frozen=True)
class OutputPaths:
    root: Path
    raw: Path


class ArtifactExporter:
    def __init__(self, output_root: Path | str) -> None:
        self.output_root = Path(output_root)

    def export(
        self,
        document_id: str,
        source: ResolvedSource,
        parsed: ParsedDocument,
        package: AgentReadyPackage | None,
        quality_report: dict[str, Any] | BaseModel,
        run_record: dict[str, Any] | BaseModel,
    ) -> OutputPaths:
        try:
            root = self._create_run_directory(document_id)
            raw_dir = root / "raw"
            parsed_dir = root / "parsed"
            raw_dir.mkdir()
            parsed_dir.mkdir()
            raw_path = raw_dir / Path(source.filename).name
            self._atomic_bytes(raw_path, source.raw_bytes)
            self._atomic_text(parsed_dir / "document.md", parsed.markdown)
            self._atomic_json(
                parsed_dir / "content-blocks.json",
                [block.model_dump(mode="json") for block in parsed.content_blocks],
            )
            self._atomic_json(root / "quality-report.json", self._jsonable(quality_report))
            self._atomic_json(root / "run.json", self._redact(self._jsonable(run_record)))
            if package is not None:
                self._atomic_json(root / "agent-ready.json", package.model_dump(mode="json"))
                self._atomic_text(root / "agent-ready.md", self._markdown(package))
            return OutputPaths(root=root, raw=raw_path)
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(
                ErrorCode.EXPORT_FAILED,
                f"Failed to export artifacts: {exc}",
                stage="export",
            ) from exc

    def export_failure(
        self,
        *,
        error: PipelineError,
        run_record: dict[str, Any] | BaseModel,
    ) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        root = self._create_run_directory(f"failed-{timestamp}-{uuid.uuid4().hex[:8]}")
        self._atomic_json(
            root / "quality-report.json",
            {"gate_status": "not_run", "error": error.as_dict()},
        )
        self._atomic_json(root / "run.json", self._redact(self._jsonable(run_record)))
        return root

    def _create_run_directory(self, document_id: str) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        for index in range(1, 10000):
            name = document_id if index == 1 else f"{document_id}-{index}"
            candidate = self.output_root / name
            try:
                candidate.mkdir()
                return candidate
            except FileExistsError:
                continue
        raise RuntimeError("unable to allocate output directory")

    @staticmethod
    def _jsonable(value: dict[str, Any] | BaseModel) -> Any:
        return value.model_dump(mode="json") if isinstance(value, BaseModel) else value

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = key.casefold()
                if any(
                    secret in normalized
                    for secret in ("api_key", "authorization", "token", "secret")
                ):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = cls._redact(item)
            return result
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value

    @staticmethod
    def _atomic_bytes(path: Path, value: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp_name).replace(path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @classmethod
    def _atomic_text(cls, path: Path, value: str) -> None:
        cls._atomic_bytes(path, value.encode("utf-8"))

    @classmethod
    def _atomic_json(cls, path: Path, value: Any) -> None:
        cls._atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _markdown(package: AgentReadyPackage) -> str:
        source_label = package.source.url or package.source.domain or package.source.source_type
        lines = [
            f"# Agent-ready Data: {package.id}",
            "",
            f"- Status: {package.status}",
            f"- Quality: {package.quality.quality_level} ({package.quality.intrinsic_score:.2f})",
            f"- Source: {source_label}",
            "",
            "## Summary",
            "",
            package.knowledge.summary,
            "",
            "## Key points",
            "",
        ]
        lines.extend(f"- {point}" for point in package.knowledge.key_points)
        lines.extend(["", "## Claims", ""])
        for claim in package.knowledge.claims:
            lines.append(f"- {claim.text} [{claim.verification_status}]")
            if claim.evidence:
                location = claim.evidence.location
                place = (
                    f"page {location.page}" if location.page else f"offset {location.start_offset}"
                )
                lines.append(f"  - Evidence ({place}): {claim.evidence.quote}")
        return "\n".join(lines).rstrip() + "\n"
