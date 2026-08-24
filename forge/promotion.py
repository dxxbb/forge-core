"""Deterministic state for Evidence-to-Asset Promotion.

The agent supplies semantic judgment; this module owns durable observations,
candidate admission, lifecycle transitions, expiry, and review metrics.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


OBSERVATION_DIR = Path("system") / "observations"
CANDIDATE_DIR = Path("system") / "candidates"
OBSERVATION_SIGNAL_TYPES = {
    "owner-correction",
    "observed-failure",
    "unresolved-conflict",
    "owner-deferred",
}


@dataclass
class Observation:
    id: str
    theme: str
    signal_type: str
    source_contexts: list[str]
    repeat_if: str
    route_gap: str
    state: str
    created_at: str
    last_seen_at: str
    expires_at: str
    event_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    candidate_id: str = ""
    closed_reason: str = ""
    path: Path | None = None

    @property
    def independent_events(self) -> int:
        return len(self.event_ids)


@dataclass
class Candidate:
    id: str
    title: str
    state: str
    ground: str
    created_at: str
    decided_at: str
    event_ids: list[str]
    evidence: list[str]
    source_context: str
    existing_coverage: str
    asset_fit: str
    promotion_rationale: str
    expected_effect: str
    decision_question: str
    problem: str
    proposal: str
    scope: str
    exclusions: list[str]
    target: str
    anchor: str
    mode: str
    proposed_text: str
    verification: str
    owner_request: str = ""
    risk_invariant: str = ""
    risk_failure: str = ""
    observation_id: str = ""
    decision_note: str = ""
    ledger_entry: str = ""
    revisions: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    path: Path | None = None
    qualification: str = "qualified"
    qualification_issues: list[str] = field(default_factory=list)

    @property
    def reviewable(self) -> bool:
        return self.state == "pending" and self.qualification == "qualified"


def observation_dir(root: Path) -> Path:
    return Path(root).resolve() / OBSERVATION_DIR


def candidate_dir(root: Path) -> Path:
    return Path(root).resolve() / CANDIDATE_DIR


def record_observation(
    root: Path,
    *,
    theme: str,
    signal_type: str,
    source_context: str,
    repeat_if: str,
    route_gap: str,
    event_ids: list[str],
    evidence: list[str],
    note: str = "",
    expires_days: int = 30,
    now: datetime | None = None,
) -> Observation:
    """Create or refresh one actual unresolved signal, grouped by theme."""
    if not theme.strip():
        raise ValueError("observation theme is required")
    signal_type = signal_type.strip()
    if signal_type not in OBSERVATION_SIGNAL_TYPES:
        allowed = "|".join(sorted(OBSERVATION_SIGNAL_TYPES))
        raise ValueError(f"observation signal type must be {allowed}")
    required_context = {
        "source context": source_context,
        "repeat if": repeat_if,
        "route gap": route_gap,
    }
    missing = [name for name, value in required_context.items() if not value.strip()]
    if missing:
        raise ValueError("observation missing required field(s): " + ", ".join(missing))
    if expires_days < 1:
        raise ValueError("expires_days must be at least 1")
    event_ids = _clean_event_ids(event_ids)
    if not event_ids:
        raise ValueError("at least one stable event id is required")
    evidence = _clean_refs(evidence)
    if not evidence:
        raise ValueError("at least one evidence reference is required")
    now = now or datetime.now().astimezone()
    obs_id = _stable_id("obs", theme)
    existing = next((o for o in list_observations(root, include_closed=True) if o.id == obs_id), None)
    if existing is None:
        obs = Observation(
            id=obs_id,
            theme=theme.strip(),
            signal_type=signal_type,
            source_contexts=[source_context.strip()],
            repeat_if=repeat_if.strip(),
            route_gap=route_gap.strip(),
            state="open",
            created_at=_iso(now),
            last_seen_at=_iso(now),
            expires_at=_iso(now + timedelta(days=expires_days)),
            event_ids=event_ids,
            evidence=evidence,
            notes=[note.strip()] if note.strip() else [],
        )
    else:
        obs = existing
        if obs.state == "promoted":
            raise ValueError(
                "observation already promoted; route new evidence as covered or draft a revision candidate"
            )
        obs.theme = theme.strip()
        if obs.signal_type not in {"", "legacy", signal_type}:
            raise ValueError(
                "observation signal type changed; use a distinct theme for a different signal"
            )
        obs.signal_type = signal_type
        if source_context.strip() not in obs.source_contexts:
            obs.source_contexts.append(source_context.strip())
        obs.repeat_if = repeat_if.strip()
        obs.route_gap = route_gap.strip()
        obs.state = "open"
        obs.last_seen_at = _iso(now)
        obs.expires_at = _iso(now + timedelta(days=expires_days))
        obs.event_ids = _clean_event_ids(obs.event_ids + event_ids)
        obs.evidence = _clean_refs(obs.evidence + evidence)
        if note.strip() and note.strip() not in obs.notes:
            obs.notes.append(note.strip())
        obs.closed_reason = ""
    _write_observation(root, obs)
    return obs


def list_observations(root: Path, *, include_closed: bool = False) -> list[Observation]:
    out: list[Observation] = []
    directory = observation_dir(root)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("obs-*.md")):
        fm = _load_frontmatter(path, "observation")
        if fm is None:
            continue
        obs_id = str(fm.get("id") or path.stem)
        evidence = _clean_refs([str(x) for x in (fm.get("evidence") or [])])
        event_ids = _clean_event_ids([str(x) for x in (fm.get("event_ids") or [])])
        if not event_ids and evidence:
            event_ids = [f"legacy-observation:{obs_id}"]
        obs = Observation(
            id=obs_id,
            theme=str(fm.get("theme") or ""),
            signal_type=str(fm.get("signal_type") or "legacy"),
            source_contexts=[str(x) for x in (fm.get("source_contexts") or [])],
            repeat_if=str(fm.get("repeat_if") or "legacy observation; not recorded"),
            route_gap=str(fm.get("route_gap") or "legacy observation; not recorded"),
            state=str(fm.get("state") or ""),
            created_at=str(fm.get("created_at") or ""),
            last_seen_at=str(fm.get("last_seen_at") or ""),
            expires_at=str(fm.get("expires_at") or ""),
            event_ids=event_ids,
            evidence=evidence,
            notes=[str(x) for x in (fm.get("notes") or [])],
            candidate_id=str(fm.get("candidate_id") or ""),
            closed_reason=str(fm.get("closed_reason") or ""),
            path=path,
        )
        if include_closed or obs.state == "open":
            out.append(obs)
    return out


def expire_observations(root: Path, *, now: datetime | None = None) -> list[str]:
    """Close stale observations while retaining their evidence on disk."""
    now = now or datetime.now().astimezone()
    expired: list[str] = []
    for obs in list_observations(root):
        if obs.candidate_id:
            candidate = get_candidate(root, obs.candidate_id)
            if candidate is not None and candidate.state == "pending":
                continue
        try:
            deadline = datetime.fromisoformat(obs.expires_at)
        except ValueError:
            continue
        comparable_now = now.astimezone(deadline.tzinfo) if deadline.tzinfo else now.replace(tzinfo=None)
        if comparable_now < deadline:
            continue
        obs.state = "closed"
        obs.closed_reason = "expired"
        _write_observation(root, obs)
        expired.append(obs.id)
    return expired


def create_candidate(
    root: Path,
    *,
    title: str,
    ground: str,
    event_ids: list[str],
    evidence: list[str],
    source_context: str,
    existing_coverage: str,
    promotion_rationale: str,
    expected_effect: str,
    decision_question: str,
    problem: str,
    proposal: str,
    scope: str,
    exclusions: list[str],
    target: str,
    anchor: str,
    mode: str,
    proposed_text: str,
    verification: str,
    asset_fit: str = "",
    owner_request: str = "",
    risk_invariant: str = "",
    risk_failure: str = "",
    observation_id: str = "",
    now: datetime | None = None,
) -> Candidate:
    """Admit one review card only when its evidence and boundaries are explicit."""
    ground = ground.strip()
    if ground not in {"repeated", "owner-directed"}:
        raise ValueError(
            "ground must be repeated|owner-directed; high-risk is a priority signal, "
            "not independent evidence that a durable owner asset is needed"
        )
    event_ids = _clean_event_ids(event_ids)
    if not event_ids:
        raise ValueError("candidate requires at least one stable event id")
    evidence = _clean_refs(evidence)
    if not evidence:
        raise ValueError("candidate requires at least one evidence reference")
    if ground == "repeated" and len(event_ids) < 2:
        raise ValueError("repeated ground requires two independent events")
    if ground == "owner-directed" and not owner_request.strip():
        raise ValueError("owner-directed ground requires the exact long-term owner request")
    required = {
        "title": title,
        "source_context": source_context,
        "existing_coverage": existing_coverage,
        "asset_fit": asset_fit,
        "promotion_rationale": promotion_rationale,
        "expected_effect": expected_effect,
        "decision_question": decision_question,
        "problem": problem,
        "proposal": proposal,
        "scope": scope,
        "target": target,
        "proposed_text": proposed_text,
        "verification": verification,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise ValueError("candidate missing required field(s): " + ", ".join(missing))
    exclusions = [x.strip() for x in exclusions if x.strip()]
    if not exclusions:
        raise ValueError("candidate requires at least one exclusion")
    if mode not in {"create", "replace", "append"}:
        raise ValueError("mode must be create|replace|append")
    if observation_id:
        observation = next(
            (o for o in list_observations(root, include_closed=True) if o.id == observation_id),
            None,
        )
        if observation is None:
            raise ValueError(f"observation not found: {observation_id}")
        if not set(event_ids).issubset(set(observation.event_ids)):
            raise ValueError("candidate event ids must be present on its observation")
        if not set(evidence).issubset(set(observation.evidence)):
            raise ValueError("candidate evidence must be present on its observation")
    now = now or datetime.now().astimezone()
    candidate_id = _stable_id("cand", f"{title}\n{target}\n{proposal}")
    if any(c.id == candidate_id for c in list_candidates(root, include_decided=True)):
        raise ValueError(f"candidate already exists: {candidate_id}")
    candidate = Candidate(
        id=candidate_id,
        title=title.strip(),
        state="pending",
        ground=ground,
        created_at=_iso(now),
        decided_at="",
        event_ids=event_ids,
        evidence=evidence,
        source_context=source_context.strip(),
        existing_coverage=existing_coverage.strip(),
        asset_fit=asset_fit.strip(),
        promotion_rationale=promotion_rationale.strip(),
        expected_effect=expected_effect.strip(),
        decision_question=decision_question.strip(),
        problem=problem.strip(),
        proposal=proposal.strip(),
        scope=scope.strip(),
        exclusions=exclusions,
        target=target.strip(),
        anchor=anchor.strip(),
        mode=mode,
        proposed_text=proposed_text.rstrip("\n"),
        verification=verification.strip(),
        owner_request=owner_request.strip(),
        risk_invariant=risk_invariant.strip(),
        risk_failure=risk_failure.strip(),
        observation_id=observation_id,
    )
    _write_candidate(root, candidate)
    if observation_id:
        observation.candidate_id = candidate.id  # type: ignore[union-attr]
        _write_observation(root, observation)  # type: ignore[arg-type]
    return candidate


def list_candidates(root: Path, *, include_decided: bool = False) -> list[Candidate]:
    out: list[Candidate] = []
    directory = candidate_dir(root)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("cand-*.md")):
        fm = _load_frontmatter(path, "candidate-asset")
        if fm is None:
            continue
        patch = fm.get("patch") or {}
        candidate_id = str(fm.get("id") or path.stem)
        evidence = _clean_refs([str(x) for x in (fm.get("evidence") or [])])
        event_ids = _clean_event_ids([str(x) for x in (fm.get("event_ids") or [])])
        if not event_ids and evidence:
            event_ids = [f"legacy-candidate:{candidate_id}"]
        candidate = Candidate(
            id=candidate_id,
            title=str(fm.get("title") or ""),
            state=str(fm.get("state") or ""),
            ground=str(fm.get("ground") or ""),
            created_at=str(fm.get("created_at") or ""),
            decided_at=str(fm.get("decided_at") or ""),
            event_ids=event_ids,
            evidence=evidence,
            source_context=str(fm.get("source_context") or ""),
            existing_coverage=str(fm.get("existing_coverage") or ""),
            asset_fit=str(fm.get("asset_fit") or ""),
            promotion_rationale=str(fm.get("promotion_rationale") or ""),
            expected_effect=str(fm.get("expected_effect") or ""),
            decision_question=str(fm.get("decision_question") or ""),
            problem=str(fm.get("problem") or ""),
            proposal=str(fm.get("proposal") or ""),
            scope=str(fm.get("scope") or ""),
            exclusions=[str(x) for x in (fm.get("exclusions") or [])],
            target=str(patch.get("target") or ""),
            anchor=str(patch.get("anchor") or ""),
            mode=str(patch.get("mode") or ""),
            proposed_text=str(patch.get("proposed_text") or ""),
            verification=str(fm.get("verification") or ""),
            owner_request=str(fm.get("owner_request") or ""),
            risk_invariant=str(fm.get("risk_invariant") or ""),
            risk_failure=str(fm.get("risk_failure") or ""),
            observation_id=str(fm.get("observation_id") or ""),
            decision_note=str(fm.get("decision_note") or ""),
            ledger_entry=str(fm.get("ledger_entry") or ""),
            revisions=[dict(x) for x in (fm.get("revisions") or [])],
            feedback=[dict(x) for x in (fm.get("feedback") or [])],
            path=path,
        )
        candidate.qualification_issues = _candidate_qualification_issues(candidate)
        candidate.qualification = (
            "legacy-unqualified" if candidate.qualification_issues else "qualified"
        )
        if include_decided or candidate.state == "pending":
            out.append(candidate)
    return out


def get_candidate(root: Path, candidate_id: str) -> Candidate | None:
    return next(
        (c for c in list_candidates(root, include_decided=True) if c.id == candidate_id),
        None,
    )


def revise_candidate(
    root: Path,
    candidate_id: str,
    *,
    problem: str | None = None,
    source_context: str | None = None,
    existing_coverage: str | None = None,
    asset_fit: str | None = None,
    promotion_rationale: str | None = None,
    expected_effect: str | None = None,
    decision_question: str | None = None,
    owner_request: str | None = None,
    risk_invariant: str | None = None,
    risk_failure: str | None = None,
    proposal: str | None = None,
    scope: str | None = None,
    exclusions: list[str] | None = None,
    target: str | None = None,
    anchor: str | None = None,
    mode: str | None = None,
    proposed_text: str | None = None,
    verification: str | None = None,
    note: str = "",
    now: datetime | None = None,
) -> Candidate:
    """Revise the same pending card after owner feedback; its id stays stable."""
    candidate = get_candidate(root, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    if candidate.state != "pending":
        raise ValueError(f"candidate is {candidate.state}, not pending")
    updates: dict[str, Any] = {
        key: value
        for key, value in {
            "problem": problem,
            "source_context": source_context,
            "existing_coverage": existing_coverage,
            "asset_fit": asset_fit,
            "promotion_rationale": promotion_rationale,
            "expected_effect": expected_effect,
            "decision_question": decision_question,
            "owner_request": owner_request,
            "risk_invariant": risk_invariant,
            "risk_failure": risk_failure,
            "proposal": proposal,
            "scope": scope,
            "target": target,
            "anchor": anchor,
            "mode": mode,
            "proposed_text": proposed_text,
            "verification": verification,
        }.items()
        if value is not None
    }
    if exclusions is not None:
        updates["exclusions"] = [x.strip() for x in exclusions if x.strip()]
    if not updates:
        raise ValueError("candidate revision has no changes")
    for name in {
        "problem",
        "source_context",
        "existing_coverage",
        "asset_fit",
        "promotion_rationale",
        "expected_effect",
        "decision_question",
        "proposal",
        "scope",
        "target",
        "proposed_text",
        "verification",
    }:
        if name in updates and not str(updates[name]).strip():
            raise ValueError(f"candidate revision cannot clear {name}")
    if "exclusions" in updates and not updates["exclusions"]:
        raise ValueError("candidate revision requires at least one exclusion")
    if "mode" in updates and updates["mode"] not in {"create", "replace", "append"}:
        raise ValueError("mode must be create|replace|append")
    future_owner_request = str(updates.get("owner_request", candidate.owner_request)).strip()
    if candidate.ground == "owner-directed" and not future_owner_request:
        raise ValueError("owner-directed ground requires the exact long-term owner request")
    future_risk_invariant = str(
        updates.get("risk_invariant", candidate.risk_invariant)
    ).strip()
    future_risk_failure = str(updates.get("risk_failure", candidate.risk_failure)).strip()
    if candidate.ground == "high-risk" and not (
        future_risk_invariant and future_risk_failure
    ):
        raise ValueError(
            "high-risk ground requires a verifiable invariant and failure mode"
        )
    changed: list[str] = []
    for name, value in updates.items():
        normalized = value.rstrip("\n") if name == "proposed_text" else value
        if getattr(candidate, name) != normalized:
            setattr(candidate, name, normalized)
            changed.append(name)
    if not changed:
        raise ValueError("candidate revision does not change the card")
    candidate.revisions.append(
        {
            "at": _iso(now or datetime.now().astimezone()),
            "fields": changed,
            "note": note.strip(),
        }
    )
    _write_candidate(root, candidate)
    return candidate


def transition_candidate(
    root: Path,
    candidate_id: str,
    state: str,
    *,
    note: str = "",
    ledger_entry: str = "",
    now: datetime | None = None,
) -> Candidate:
    if state not in {"promoted", "rejected", "observing"}:
        raise ValueError("candidate state must be promoted|rejected|observing")
    candidate = get_candidate(root, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    if candidate.state != "pending":
        raise ValueError(f"candidate is {candidate.state}, not pending")
    candidate.state = state
    candidate.decided_at = _iso(now or datetime.now().astimezone())
    candidate.decision_note = note.strip()
    candidate.ledger_entry = ledger_entry
    _write_candidate(root, candidate)
    if candidate.observation_id:
        observation = next(
            (
                o
                for o in list_observations(root, include_closed=True)
                if o.id == candidate.observation_id
            ),
            None,
        )
        if observation is not None:
            if state == "promoted":
                observation.state = "promoted"
                observation.closed_reason = ""
                _write_observation(root, observation)
            elif state == "rejected":
                observation.state = "closed"
                observation.closed_reason = "candidate-rejected"
                _write_observation(root, observation)
    return candidate


def return_candidate_to_observation(
    root: Path,
    candidate_id: str,
    *,
    note: str = "",
    expires_days: int = 30,
    now: datetime | None = None,
) -> tuple[Candidate, Observation]:
    candidate = get_candidate(root, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    existing = next(
        (
            o
            for o in list_observations(root, include_closed=True)
            if o.id == candidate.observation_id
        ),
        None,
    )
    observation = record_observation(
        root,
        theme=existing.theme if existing is not None else candidate.problem,
        signal_type=existing.signal_type if existing is not None else "owner-deferred",
        source_context=candidate.source_context,
        repeat_if=(
            "another independent event matches the candidate problem and scope"
        ),
        route_gap=(
            "the owner explicitly deferred promotion until stronger recurrence evidence exists"
        ),
        event_ids=candidate.event_ids,
        evidence=candidate.evidence,
        note=note or f"候选 {candidate.id} 退回观察",
        expires_days=expires_days,
        now=now,
    )
    candidate.observation_id = observation.id
    _write_candidate(root, candidate)
    candidate = transition_candidate(root, candidate_id, "observing", note=note, now=now)
    observation.candidate_id = candidate.id
    _write_observation(root, observation)
    return candidate, observation


def record_asset_feedback(
    root: Path,
    candidate_id: str,
    *,
    outcome: str,
    evidence: list[str],
    note: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attach and scoped-commit real-use evidence to a promoted asset card."""
    if outcome not in {"effective", "revise", "retire"}:
        raise ValueError("feedback outcome must be effective|revise|retire")
    candidate = get_candidate(root, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate not found: {candidate_id}")
    if candidate.state != "promoted":
        raise ValueError(f"candidate is {candidate.state}, not promoted")
    refs = _clean_refs(evidence)
    if not refs:
        raise ValueError("asset feedback requires real-use evidence")
    feedback: dict[str, Any] = {
        "outcome": outcome,
        "evidence": refs,
        "note": note.strip(),
        "at": _iso(now or datetime.now().astimezone()),
    }
    assert candidate.path is not None
    original = candidate.path.read_text(encoding="utf-8")
    candidate.feedback.append(feedback)
    _write_candidate(root, candidate)
    try:
        from forge.gate import _git

        relpath = str(candidate.path.relative_to(Path(root).resolve()))
        _git.add(Path(root).resolve(), [relpath])
        _git.commit(
            Path(root).resolve(),
            f"asset feedback: {candidate.id} {outcome}",
            trailers={"Candidate-Id": candidate.id},
        )
    except Exception:
        candidate.path.write_text(original, encoding="utf-8")
        try:
            _git.git(Path(root).resolve(), ["reset", "--", relpath])
        except Exception:
            pass
        raise
    return feedback


def promotion_metrics(root: Path) -> dict[str, Any]:
    candidates = list_candidates(root, include_decided=True)
    decided = [c for c in candidates if c.state in {"promoted", "rejected", "observing"}]
    promoted = [c for c in decided if c.state == "promoted"]
    feedback_counts: dict[str, int] = {}
    review_seconds: list[float] = []
    for candidate in decided:
        try:
            review_seconds.append(
                max(
                    0.0,
                    (
                        datetime.fromisoformat(candidate.decided_at)
                        - datetime.fromisoformat(candidate.created_at)
                    ).total_seconds(),
                )
            )
        except ValueError:
            pass
        for item in candidate.feedback:
            outcome = str(item.get("outcome") or "")
            if outcome:
                feedback_counts[outcome] = feedback_counts.get(outcome, 0) + 1
    return {
        "decided": len(decided),
        "acceptance_rate": round(len(promoted) / len(decided), 3) if decided else None,
        "average_review_seconds": round(sum(review_seconds) / len(review_seconds), 1)
        if review_seconds
        else None,
        "used_assets": sum(1 for c in promoted if c.feedback),
        "feedback_counts": feedback_counts,
    }


def _write_observation(root: Path, obs: Observation) -> None:
    path = observation_dir(root) / f"{obs.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {
        "kind": "observation",
        "id": obs.id,
        "theme": obs.theme,
        "signal_type": obs.signal_type,
        "source_contexts": obs.source_contexts,
        "repeat_if": obs.repeat_if,
        "route_gap": obs.route_gap,
        "state": obs.state,
        "created_at": obs.created_at,
        "last_seen_at": obs.last_seen_at,
        "expires_at": obs.expires_at,
        "event_ids": obs.event_ids,
        "evidence": obs.evidence,
        "notes": obs.notes,
        "candidate_id": obs.candidate_id,
        "closed_reason": obs.closed_reason,
    }
    path.write_text(
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + f"# {obs.theme}\n\n"
        + f"独立证据: {obs.independent_events} · 状态: {obs.state}\n",
        encoding="utf-8",
    )
    obs.path = path


def _write_candidate(root: Path, candidate: Candidate) -> None:
    path = candidate_dir(root) / f"{candidate.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {
        "kind": "candidate-asset",
        "id": candidate.id,
        "title": candidate.title,
        "state": candidate.state,
        "ground": candidate.ground,
        "created_at": candidate.created_at,
        "decided_at": candidate.decided_at,
        "event_ids": candidate.event_ids,
        "evidence": candidate.evidence,
        "source_context": candidate.source_context,
        "existing_coverage": candidate.existing_coverage,
        "asset_fit": candidate.asset_fit,
        "promotion_rationale": candidate.promotion_rationale,
        "expected_effect": candidate.expected_effect,
        "decision_question": candidate.decision_question,
        "owner_request": candidate.owner_request,
        "risk_invariant": candidate.risk_invariant,
        "risk_failure": candidate.risk_failure,
        "problem": candidate.problem,
        "proposal": candidate.proposal,
        "scope": candidate.scope,
        "exclusions": candidate.exclusions,
        "verification": candidate.verification,
        "observation_id": candidate.observation_id,
        "decision_note": candidate.decision_note,
        "ledger_entry": candidate.ledger_entry,
        "revisions": candidate.revisions,
        "feedback": candidate.feedback,
        "patch": {
            "target": candidate.target,
            "anchor": candidate.anchor,
            "mode": candidate.mode,
            "proposed_text": candidate.proposed_text,
        },
    }
    path.write_text(
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + f"# {candidate.title}\n\n"
        + f"## Source context\n\n{candidate.source_context}\n\n"
        + f"## Existing coverage\n\n{candidate.existing_coverage}\n\n"
        + f"## Asset fit\n\n{candidate.asset_fit}\n\n"
        + f"## Promotion rationale\n\n{candidate.promotion_rationale}\n\n"
        + f"## Problem\n\n{candidate.problem}\n\n"
        + f"## Proposal\n\n{candidate.proposal}\n\n"
        + f"## Scope\n\n{candidate.scope}\n\n"
        + f"## Expected effect\n\n{candidate.expected_effect}\n\n"
        + f"## Decision question\n\n{candidate.decision_question}\n\n"
        + "## Exclusions\n\n"
        + "\n".join(f"- {item}" for item in candidate.exclusions)
        + "\n",
        encoding="utf-8",
    )
    candidate.path = path


_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)


def _load_frontmatter(path: Path, kind: str) -> dict[str, Any] | None:
    match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    if match is None:
        return None
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict) or fm.get("kind") != kind:
        return None
    return fm


def _clean_refs(refs: list[str]) -> list[str]:
    return list(dict.fromkeys(r.strip() for r in refs if r.strip()))


def _candidate_qualification_issues(candidate: Candidate) -> list[str]:
    """Return current review-publication failures without rewriting history."""
    issues: list[str] = []
    required = {
        "title": candidate.title,
        "source_context": candidate.source_context,
        "existing_coverage": candidate.existing_coverage,
        "asset_fit": candidate.asset_fit,
        "promotion_rationale": candidate.promotion_rationale,
        "expected_effect": candidate.expected_effect,
        "decision_question": candidate.decision_question,
        "problem": candidate.problem,
        "proposal": candidate.proposal,
        "scope": candidate.scope,
        "target": candidate.target,
        "proposed_text": candidate.proposed_text,
        "verification": candidate.verification,
    }
    issues.extend(name for name, value in required.items() if not value.strip())
    if candidate.ground not in {"repeated", "owner-directed"}:
        issues.append("ground")
    if not candidate.event_ids:
        issues.append("event_ids")
    if any(event_id.startswith("legacy-candidate:") for event_id in candidate.event_ids):
        issues.append("event_ids")
    if not candidate.evidence:
        issues.append("evidence")
    if candidate.ground == "repeated" and len(set(candidate.event_ids)) < 2:
        issues.append("ground")
    if candidate.ground == "owner-directed" and not candidate.owner_request.strip():
        issues.append("owner_request")
    if not candidate.exclusions:
        issues.append("exclusions")
    if candidate.mode not in {"create", "replace", "append"}:
        issues.append("mode")
    return list(dict.fromkeys(issues))


_EVENT_ID_RE = re.compile(r"[a-z][a-z0-9-]*:[^\s]+\Z")


def _clean_event_ids(event_ids: list[str]) -> list[str]:
    cleaned = _clean_refs(event_ids)
    invalid = [event_id for event_id in cleaned if not _EVENT_ID_RE.fullmatch(event_id)]
    if invalid:
        raise ValueError(
            "event ids must be stable scheme:value identifiers, not evidence paths: "
            + ", ".join(invalid)
        )
    return cleaned


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.strip().casefold().encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32]
    return f"{prefix}-{slug + '-' if slug else ''}{digest}"


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")
