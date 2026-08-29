"""Evidence-based learning proposals for MakeCrew.

The engine records outcomes and proposes changes; applying a proposal remains an
explicit integration step so existing role files stay intact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from statistics import mean
from time import time


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class LearningRecord:
    task_id: str
    employee_id: str
    score: int
    feedback: str
    root_cause: str = ""
    at: float = field(default_factory=time)


@dataclass
class LearningProposal:
    proposal_id: str
    scope: str
    target: str
    change: str
    evidence_task_ids: list[str]
    baseline_score: float | None = None
    candidate_score: float | None = None
    status: str = ProposalStatus.PROPOSED


class LearningEngine:
    """Collect outcomes and produce small, reviewable improvement proposals."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self.records: list[LearningRecord] = []
        self.proposals: list[LearningProposal] = []
        if self._path and self._path.exists():
            self._load()

    def _persist(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [asdict(item) for item in self.records], "proposals": [asdict(item) for item in self.proposals]}
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"学习记录文件无效: {self._path}") from exc
        self.records = [LearningRecord(**item) for item in payload.get("records", [])]
        self.proposals = [LearningProposal(**item) for item in payload.get("proposals", [])]

    def record(self, task_id: str, *, employee_id: str, score: int, feedback: str, root_cause: str = "") -> LearningRecord:
        if not task_id.strip() or not employee_id.strip():
            raise ValueError("任务 ID 和员工 ID 不能为空")
        if score < 1 or score > 5:
            raise ValueError("验收评分必须在 1 到 5 之间")
        item = LearningRecord(task_id.strip(), employee_id.strip(), score, feedback.strip(), root_cause.strip())
        self.records.append(item)
        self._persist()
        return item

    def propose(self) -> list[LearningProposal]:
        """Group repeated feedback by employee and turn it into proposals."""
        grouped: dict[str, list[LearningRecord]] = {}
        for item in self.records:
            if item.score < 4 and item.root_cause:
                grouped.setdefault(item.employee_id, []).append(item)
        proposals: list[LearningProposal] = []
        existing = {
            (proposal.target, tuple(sorted(proposal.evidence_task_ids)))
            for proposal in self.proposals
            if proposal.scope == "employee"
        }
        for index, (employee_id, records) in enumerate(grouped.items(), start=1):
            root_causes = "、".join(dict.fromkeys(item.root_cause for item in records))
            evidence_task_ids = [item.task_id for item in records]
            if (employee_id, tuple(sorted(evidence_task_ids))) in existing:
                continue
            proposal = LearningProposal(
                proposal_id=f"LP-{len(self.proposals) + index:04d}",
                scope="employee",
                target=employee_id,
                change=f"为该员工增加针对“{root_causes}”的前置检查和验收步骤",
                evidence_task_ids=evidence_task_ids,
            )
            proposals.append(proposal)
        self.proposals.extend(proposals)
        self._persist()
        return proposals

    def propose_from_scores(self, proposal_id: str, *, baseline: list[int], candidate: list[int]) -> list[LearningProposal]:
        """Approve a candidate only when its average score improves the baseline."""
        if not baseline or not candidate or any(score < 1 or score > 5 for score in baseline + candidate):
            raise ValueError("回放评分必须是 1 到 5 的非空列表")
        baseline_score, candidate_score = mean(baseline), mean(candidate)
        status = ProposalStatus.APPROVED if candidate_score > baseline_score else ProposalStatus.REJECTED
        proposal = LearningProposal(
            proposal_id=proposal_id,
            scope="replay",
            target="routing-and-skills",
            change="采用候选改进方案" if status == ProposalStatus.APPROVED else "保留现有方案",
            evidence_task_ids=[],
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            status=status,
        )
        self.proposals.append(proposal)
        self._persist()
        return [proposal]

    def export(self) -> dict[str, list[dict]]:
        return {"records": [asdict(item) for item in self.records], "proposals": [asdict(item) for item in self.proposals]}
