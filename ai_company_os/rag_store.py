"""Incremental text indexing for the portable AgentFlow OS RAG contract."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .rag import HybridRetriever, KnowledgeRecord, RetrievalScope


TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}


def plan_directory(source_dir: str | Path) -> dict[str, Any]:
    """Inspect directory metadata only; never opens or hashes file contents."""
    root = Path(source_dir).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    supported: dict[str, int] = {}
    ignored: dict[str, int] = {}
    files = 0
    bytes_total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold() or "[no extension]"
        bucket = supported if path.suffix.casefold() in TEXT_SUFFIXES else ignored
        bucket[suffix] = bucket.get(suffix, 0) + 1
        if bucket is supported:
            files += 1
            bytes_total += path.stat().st_size
    return {
        "source_dir": str(root),
        "supported_files": files,
        "supported_bytes": bytes_total,
        "supported_extensions": supported,
        "ignored_files": sum(ignored.values()),
        "ignored_extensions": ignored,
        "content_read": False,
        "index_written": False,
    }


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
            try:
                Path(source).relative_to(root)
                under_root = True
            except ValueError:
                under_root = False
            if under_root and source not in current_sources:
                for record_id in self.files[source].get("record_ids", []):
                    self.records.pop(record_id, None)
                del self.files[source]
                removed += 1
        self.save()
        return {"source_dir": str(root), "added": added, "changed": changed, "skipped": skipped, "removed": removed, "chunks": chunks, "total_records": len(self.records)}

    def search(self, query: str, scope: RetrievalScope):
        return HybridRetriever(self.records.values()).search(query, scope)

    def search_adaptive(self, query: str, scope: RetrievalScope, *, min_score: float = 0.2, score_margin: float = 0.18, max_chars: int | None = None):
        return HybridRetriever(self.records.values()).search_adaptive(
            query,
            scope,
            min_score=min_score,
            score_margin=score_margin,
            max_chars=max_chars,
        )

    def audit(self) -> dict[str, Any]:
        statuses: dict[str, int] = {}
        scopes: dict[str, int] = {}
        for record in self.records.values():
            statuses[record.status] = statuses.get(record.status, 0) + 1
            scopes[record.scope] = scopes.get(record.scope, 0) + 1
        return {"index": str(self.path), "version": self.VERSION, "files": len(self.files), "records": len(self.records), "statuses": statuses, "scopes": scopes, "quality": self.audit_quality()}

    def audit_quality(self) -> dict[str, Any]:
        """Report quality risks without deleting or rewriting any knowledge."""
        duplicate_groups: list[dict[str, Any]] = []
        by_content: dict[str, list[KnowledgeRecord]] = {}
        for record in self.records.values():
            normalized = " ".join(record.content.casefold().split())
            by_content.setdefault(normalized, []).append(record)
        for normalized, records in by_content.items():
            if len(records) > 1:
                duplicate_groups.append({"fingerprint": hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16], "record_ids": [record.record_id for record in records], "sources": sorted({record.source for record in records})})

        conflict_groups: list[dict[str, Any]] = []
        by_title: dict[tuple[str, str, str], list[KnowledgeRecord]] = {}
        for record in self.records.values():
            key = (record.scope, record.project_id, (record.title or record.record_id).casefold())
            by_title.setdefault(key, []).append(record)
        for (scope, project_id, title), records in by_title.items():
            sources = {record.source for record in records}
            contents = {" ".join(record.content.casefold().split()) for record in records}
            if len(sources) > 1 and len(contents) > 1:
                conflict_groups.append({"scope": scope, "project_id": project_id, "title": title, "record_ids": [record.record_id for record in records], "sources": sorted(sources), "action": "人工确认主版本并标记其他记录为 superseded"})

        stale_sources: list[str] = []
        missing_sources: list[str] = []
        orphan_record_ids: list[str] = []
        referenced: set[str] = set()
        for source, metadata in self.files.items():
            referenced.update(metadata.get("record_ids", []))
            parsed = urlparse(source)
            # ``urlparse`` treats ``C:\\...`` as scheme ``c``; only URLs with
            # an explicit ``://`` are remote sources in this local index.
            if "://" in source and parsed.scheme not in {"file"}:
                continue
            path = Path(source)
            if not path.exists():
                missing_sources.append(source)
            elif metadata.get("sha256") and sha256_file(path) != metadata["sha256"]:
                stale_sources.append(source)
        orphan_record_ids = sorted(set(self.records) - referenced)
        issues = len(duplicate_groups) + len(conflict_groups) + len(stale_sources) + len(missing_sources) + len(orphan_record_ids)
        return {"status": "review" if issues else "pass", "duplicate_groups": duplicate_groups, "conflict_groups": conflict_groups, "stale_sources": stale_sources, "missing_sources": missing_sources, "orphan_record_ids": orphan_record_ids, "issue_count": issues}
