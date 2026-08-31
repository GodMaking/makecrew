"""Portable, scope-aware retrieval contracts for AgentFlow OS.

The MVP deliberately uses a small lexical scorer instead of a vector database.
Hosts can replace ``HybridRetriever`` with an embedding-backed adapter while
keeping the same records, scopes, citations, and permission semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import re
from typing import Callable, Iterable, Protocol


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", re.UNICODE)
VALID_STATUSES = {"active", "draft", "superseded", "archived"}
VALID_ACTORS = {"ceo", "manager", "employee", "task"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    for item in TOKEN_RE.findall(text or ""):
        item = item.casefold()
        if not item.strip():
            continue
        terms.add(item)
        # Character bigrams give Chinese queries useful phrase-level matching
        # without requiring a heavyweight tokenizer in the dependency-free MVP.
        if re.fullmatch(r"[\u4e00-\u9fff]+", item):
            terms.update(item[index:index + 2] for index in range(len(item) - 1))
    return terms


@dataclass(frozen=True)
class KnowledgeRecord:
    """One indexed chunk with provenance and an explicit retrieval boundary."""

    record_id: str
    content: str
    source: str
    title: str = ""
    scope: str = "company"  # company, project, task
    project_id: str = ""
    allowed_actors: tuple[str, ...] = ("ceo", "manager", "employee", "task")
    status: str = "active"
    evidence: str = "F"  # F=fact, I=interpretation, H=hypothesis
    updated_at: str = field(default_factory=_now)
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.record_id.strip() or not self.content.strip() or not self.source.strip():
            raise ValueError("record_id、content 和 source 不能为空")
        if self.scope not in {"company", "project", "task"}:
            raise ValueError("scope 必须是 company、project 或 task")
        if self.scope in {"project", "task"} and not self.project_id.strip():
            raise ValueError("project/task 记录必须提供 project_id")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"status 必须是 {sorted(VALID_STATUSES)} 之一")
        if self.evidence not in {"F", "I", "H"}:
            raise ValueError("evidence 必须是 F、I 或 H")
        unknown = set(self.allowed_actors) - VALID_ACTORS
        if unknown:
            raise ValueError(f"allowed_actors 存在未知角色：{sorted(unknown)}")


@dataclass(frozen=True)
class RetrievalScope:
    """Caller boundary used before scoring; permission filtering is fail-closed."""

    actor: str
    project_ids: tuple[str, ...] = ()
    include_company: bool = True
    include_archived: bool = False
    include_inactive: bool = False
    max_results: int = 8
    max_chars: int = 20_000

    def __post_init__(self) -> None:
        if self.actor not in VALID_ACTORS:
            raise ValueError(f"actor 必须是 {sorted(VALID_ACTORS)} 之一")
        if self.max_results < 1 or self.max_results > 50:
            raise ValueError("max_results 必须在 1 到 50 之间")
        if self.max_chars < 100:
            raise ValueError("max_chars 至少为 100")


@dataclass(frozen=True)
class RetrievalHit:
    record: KnowledgeRecord
    score: float
    matched_terms: tuple[str, ...]

    def citation(self) -> dict[str, str]:
        return {
            "record_id": self.record.record_id,
            "title": self.record.title or self.record.record_id,
            "source": self.record.source,
            "updated_at": self.record.updated_at,
            "evidence": self.record.evidence,
            "scope": self.record.scope,
        }


class Retriever(Protocol):
    def upsert(self, records: Iterable[KnowledgeRecord]) -> None: ...

    def search(self, query: str, scope: RetrievalScope) -> list[RetrievalHit]: ...

    def search_adaptive(self, query: str, scope: RetrievalScope, *, min_score: float = 0.2, score_margin: float = 0.18) -> list[RetrievalHit]: ...


class SemanticScorer(Protocol):
    """Optional host callback returning normalized semantic scores by record ID."""

    def __call__(self, query: str, records: list[KnowledgeRecord]) -> dict[str, float]: ...


class HybridRetriever:
    """Small deterministic baseline: lexical relevance plus freshness bonus.

    It is intentionally replaceable. A host can implement ``Retriever`` with
    BM25/vector search without changing employee routing or memory boundaries.
    """

    def __init__(self, records: Iterable[KnowledgeRecord] = (), *, semantic_scorer: SemanticScorer | None = None, semantic_weight: float = 0.35) -> None:
        if not 0 <= semantic_weight <= 1:
            raise ValueError("semantic_weight 必须在 0 到 1 之间")
        self._records: dict[str, KnowledgeRecord] = {}
        self.semantic_scorer = semantic_scorer
        self.semantic_weight = semantic_weight
        self.upsert(records)

    def upsert(self, records: Iterable[KnowledgeRecord]) -> None:
        for record in records:
            self._records[record.record_id] = record

    def remove(self, record_ids: Iterable[str]) -> None:
        for record_id in record_ids:
            self._records.pop(record_id, None)

    def search(self, query: str, scope: RetrievalScope) -> list[RetrievalHit]:
        hits = self._rank(query, scope)
        return self._select(hits, max_results=scope.max_results, max_chars=scope.max_chars)

    def search_adaptive(
        self,
        query: str,
        scope: RetrievalScope,
        *,
        min_score: float = 0.2,
        score_margin: float = 0.18,
        max_chars: int | None = None,
    ) -> list[RetrievalHit]:
        """Expand recall until relevance and query-coverage signals are satisfied.

        ``max_results`` is intentionally ignored here. The host context budget
        remains the only size guard, while low-scoring candidates are admitted
        when they cover an otherwise missing query term.
        """
        if not 0 <= min_score <= 1:
            raise ValueError("min_score 必须在 0 到 1 之间")
        if score_margin < 0:
            raise ValueError("score_margin 不能为负数")
        hits = self._rank(query, scope)
        if not hits:
            return []
        threshold = max(min_score, hits[0].score - score_margin)
        query_terms = _terms(query)
        covered: set[str] = set()
        selected: list[RetrievalHit] = []
        chars = 0
        budget = scope.max_chars if max_chars is None else max_chars
        if budget < 100:
            raise ValueError("max_chars 至少为 100")
        for hit in hits:
            new_terms = set(hit.matched_terms) - covered
            relevant = hit.score >= threshold
            if not relevant and not new_terms:
                continue
            size = len(hit.record.content)
            if selected and chars + size > budget:
                continue
            selected.append(hit)
            chars += size
            covered.update(hit.matched_terms)
            if query_terms and query_terms.issubset(covered) and hit.score < threshold:
                break
        return selected

    def _rank(self, query: str, scope: RetrievalScope) -> list[RetrievalHit]:
        query_terms = _terms(query)
        visible = [record for record in self._records.values() if self._visible(record, scope)]
        visible_ids = {record.record_id for record in visible}
        semantic_scores: dict[str, float] = {}
        if self.semantic_scorer and visible:
            semantic_scores = self.semantic_scorer(query, visible) or {}
        if not query_terms and not any(float(score) > 0 for score in semantic_scores.values()):
            return []
        document_frequency = {
            term: sum(term in _terms(record.title + " " + record.content + " " + " ".join(record.tags)) for record in visible)
            for term in query_terms
        }
        lexical_scores: dict[str, float] = {}
        matched_terms_by_id: dict[str, tuple[str, ...]] = {}
        for record in visible:
            record_terms = _terms(record.title + " " + record.content + " " + " ".join(record.tags))
            matched = query_terms & record_terms
            if not matched:
                continue
            # IDF-like weighting keeps common words from dominating without a dependency.
            lexical = sum((1.0 + math.log((len(visible) + 1) / (document_frequency[term] + 1))) for term in matched)
            title_bonus = sum(0.35 for term in matched if term in _terms(record.title))
            freshness = 0.15 if record.status == "active" else 0.0
            lexical_scores[record.record_id] = lexical + title_bonus + freshness
            matched_terms_by_id[record.record_id] = tuple(sorted(matched))
        max_lexical = max(lexical_scores.values(), default=1.0)
        candidate_ids = set(lexical_scores) | {
            record_id
            for record_id, score in semantic_scores.items()
            if float(score) > 0 and record_id in visible_ids
        }
        hits: list[RetrievalHit] = []
        for record_id in candidate_ids:
            lexical_score = lexical_scores.get(record_id, 0.0)
            normalized_lexical = lexical_score / max_lexical
            semantic_score = min(1.0, max(0.0, float(semantic_scores.get(record_id, 0.0))))
            score = ((1 - self.semantic_weight) * normalized_lexical) + (self.semantic_weight * semantic_score)
            hits.append(RetrievalHit(self._records[record_id], round(score, 6), matched_terms_by_id.get(record_id, ())))
        hits.sort(key=lambda hit: (-hit.score, hit.record.record_id))
        return hits

    @staticmethod
    def _select(hits: list[RetrievalHit], *, max_results: int, max_chars: int) -> list[RetrievalHit]:
        selected: list[RetrievalHit] = []
        chars = 0
        for hit in hits:
            if len(selected) >= max_results:
                break
            size = len(hit.record.content)
            if selected and chars + size > max_chars:
                continue
            selected.append(hit)
            chars += size
        return selected

    @staticmethod
    def _visible(record: KnowledgeRecord, scope: RetrievalScope) -> bool:
        if scope.actor not in record.allowed_actors:
            return False
        if record.status == "archived" and not scope.include_archived:
            return False
        if record.status in {"draft", "superseded"} and not scope.include_inactive:
            return False
        if record.scope == "company":
            return scope.include_company
        return record.project_id in set(scope.project_ids)


class HostRagAdapter(Protocol):
    """Optional host contract for embeddings, persistence, or remote search."""

    def list_records(self, namespace: str) -> Iterable[KnowledgeRecord]: ...

    def search(self, query: str, scope: RetrievalScope) -> list[RetrievalHit]: ...
