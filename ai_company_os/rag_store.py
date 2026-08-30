"""Incremental text indexing for the portable AgentFlow OS RAG contract."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .rag import HybridRetriever, KnowledgeRecord, RetrievalScope


TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunk_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text.strip()]:
        if len(paragraph) <= max_chars and current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current)
            current = ""
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(paragraph[index:index + max_chars] for index in range(0, len(paragraph), max_chars))
            continue
        current = paragraph if not current else f"{current}\n\n{paragraph}"
    if current:
        chunks.append(current)
    return chunks


def _record_from_dict(data: dict[str, Any]) -> KnowledgeRecord:
    data = dict(data)
    for key in ("allowed_actors", "tags"):
        data[key] = tuple(data.get(key, ()))
    return KnowledgeRecord(**data)


class JsonRagIndex:
    """Persistent index with content-hash based incremental synchronization."""

    VERSION = 1

    def __init__(self, index_path: str | Path):
        self.path = Path(index_path).expanduser().resolve()
        self.files: dict[str, dict[str, Any]] = {}
        self.records: dict[str, KnowledgeRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("version") != self.VERSION:
            raise ValueError(f"不支持的 RAG 索引版本：{payload.get('version')}")
        self.files = dict(payload.get("files", {}))
        self.records = {key: _record_from_dict(value) for key, value in payload.get("records", {}).items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "files": self.files,
            "records": {key: asdict(value) for key, value in self.records.items()},
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def sync_directory(
        self,
        source_dir: str | Path,
        *,
        scope: str = "company",
        project_id: str = "",
        allowed_actors: Iterable[str] = ("ceo", "manager", "employee", "task"),
        max_chars: int = 1200,
    ) -> dict[str, int | str]:
        root = Path(source_dir).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        actor_tuple = tuple(allowed_actors)
        current_sources: set[str] = set()
        added = changed = skipped = removed = chunks = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES:
                continue
            source = str(path)
            current_sources.add(source)
            digest = sha256_file(path)
            previous = self.files.get(source)
            if previous and previous.get("sha256") == digest:
                skipped += 1
                continue
            if previous:
                for record_id in previous.get("record_ids", []):
                    self.records.pop(record_id, None)
                changed += 1
            else:
                added += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), path.stem)
            record_ids: list[str] = []
            for position, chunk in enumerate(_chunk_text(text, max_chars)):
                record_id = hashlib.sha256(f"{source}:{digest}:{position}".encode("utf-8")).hexdigest()[:24]
                self.records[record_id] = KnowledgeRecord(
                    record_id=record_id,
                    title=title,
                    content=chunk,
                    source=source,
                    scope=scope,
                    project_id=project_id,
                    allowed_actors=actor_tuple,
                    tags=(path.stem,),
                )
                record_ids.append(record_id)
            self.files[source] = {"sha256": digest, "record_ids": record_ids, "scope": scope, "project_id": project_id}
            chunks += len(record_ids)
        for source in list(self.files):
            if source.startswith(str(root)) and source not in current_sources:
                for record_id in self.files[source].get("record_ids", []):
                    self.records.pop(record_id, None)
                del self.files[source]
                removed += 1
        self.save()
        return {"source_dir": str(root), "added": added, "changed": changed, "skipped": skipped, "removed": removed, "chunks": chunks, "total_records": len(self.records)}

    def search(self, query: str, scope: RetrievalScope):
        return HybridRetriever(self.records.values()).search(query, scope)

    def audit(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        scopes: dict[str, int] = {}
        for record in self.records.values():
            statuses[record.status] = statuses.get(record.status, 0) + 1
            scopes[record.scope] = scopes.get(record.scope, 0) + 1
        return {"index": str(self.path), "version": self.VERSION, "files": len(self.files), "records": len(self.records), "statuses": statuses, "scopes": scopes}
