"""Runtime readiness reporting for single-host production."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from gg.runtime.ledger import ReservationPhase
from gg.runtime.scheduler import DispatchStatus, TaskScheduler


class ReadinessCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    phase: ReservationPhase
    detail: str
    category: str


class RuntimeReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    database_available: bool
    dispatch_owner: bool
    reconciled: bool
    unresolved_capacity: int
    conditions: tuple[ReadinessCondition, ...] = ()


def _classify_condition(phase: ReservationPhase, detail: str) -> str:
    lowered = detail.lower()
    if phase is ReservationPhase.UNRESOLVED_CREATION:
        if "health request failed" in lowered or "connect" in lowered:
            return "provider_outage"
        return "unresolved_creation"
    if phase is ReservationPhase.TERMINATION_PENDING:
        return "pending_cleanup"
    if "confirmed lost" in lowered or "sandbox was confirmed lost" in lowered:
        return "confirmed_sandbox_loss"
    if "provider" in lowered or "detach" in lowered:
        return "provider_outage"
    return "operator_attention"


def build_readiness(
    *,
    database_available: bool,
    dispatch_owner: bool,
    dispatch: DispatchStatus,
) -> RuntimeReadiness:
    conditions = tuple(
        ReadinessCondition(
            task_id=item.task_id,
            phase=item.phase,
            detail=item.detail,
            category=_classify_condition(item.phase, item.detail),
        )
        for item in dispatch.conditions
        if item.detail is not None
    )
    unresolved = sum(
        1
        for item in conditions
        if item.category
        in {"provider_outage", "unresolved_creation", "pending_cleanup"}
    )
    ready = (
        database_available
        and dispatch_owner
        and dispatch.reconciled
        and unresolved == 0
    )
    return RuntimeReadiness(
        status="ready" if ready else "not_ready",
        database_available=database_available,
        dispatch_owner=dispatch_owner,
        reconciled=dispatch.reconciled,
        unresolved_capacity=unresolved,
        conditions=conditions,
    )


def readiness_from_scheduler(
    scheduler: TaskScheduler, *, database_available: bool
) -> RuntimeReadiness:
    return build_readiness(
        database_available=database_available,
        dispatch_owner=scheduler.owns_dispatch_lock(),
        dispatch=scheduler.status(),
    )


__all__ = [
    "ReadinessCondition",
    "RuntimeReadiness",
    "build_readiness",
    "readiness_from_scheduler",
]
