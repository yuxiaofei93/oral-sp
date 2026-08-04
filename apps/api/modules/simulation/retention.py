from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AIEvaluationRun,
    AIScoreResult,
    AssignmentStatus,
    Message,
    ModelCall,
    ScoreResult,
    SessionAssessment,
    SessionStageEvent,
    SessionStatus,
    SimulationSession,
    StageSubmission,
    TeacherReview,
)
from .services import expire_overdue_sessions


@dataclass(frozen=True)
class RetentionPreview:
    stale_active_sessions: int
    deletable_sessions: int
    messages: int
    submissions: int
    model_calls: int
    score_results: int
    teacher_reviews: int
    ai_evaluation_runs: int
    ai_score_results: int


@dataclass(frozen=True)
class RetentionResult:
    materialized_expirations: int
    deleted_sessions: int
    deleted_related_records: int


def deletable_sessions(*, now=None):
    now = now or timezone.now()
    return SimulationSession.objects.filter(
        status__in=(SessionStatus.COMPLETED, SessionStatus.EXPIRED),
        retention_expires_at__lte=now,
        assignment__deadline_at__lte=now,
    )


def retention_preview(*, now=None) -> RetentionPreview:
    now = now or timezone.now()
    stale_active = SimulationSession.objects.filter(status=SessionStatus.ACTIVE).filter(
        Q(deadline_at__lte=now) | Q(assignment__status=AssignmentStatus.CLOSED)
    )
    targets = deletable_sessions(now=now)
    return RetentionPreview(
        stale_active_sessions=stale_active.count(),
        deletable_sessions=targets.count(),
        messages=Message.objects.filter(session__in=targets).count(),
        submissions=StageSubmission.objects.filter(session__in=targets).count(),
        model_calls=ModelCall.objects.filter(session__in=targets).count(),
        score_results=ScoreResult.objects.filter(session__in=targets).count(),
        teacher_reviews=TeacherReview.objects.filter(session__in=targets).count(),
        ai_evaluation_runs=AIEvaluationRun.objects.filter(session__in=targets).count(),
        ai_score_results=AIScoreResult.objects.filter(run__session__in=targets).count(),
    )


def purge_expired_sessions(*, now=None) -> RetentionResult:
    now = now or timezone.now()
    materialized = expire_overdue_sessions(now=now)
    session_ids = list(deletable_sessions(now=now).values_list("id", flat=True))
    if not session_ids:
        return RetentionResult(
            materialized_expirations=materialized,
            deleted_sessions=0,
            deleted_related_records=0,
        )

    deleted_related = 0
    with transaction.atomic():
        deleted, _ = AIScoreResult.objects.filter(run__session_id__in=session_ids).delete()
        deleted_related += deleted
        for model in (
            AIEvaluationRun,
            ScoreResult,
            SessionAssessment,
            TeacherReview,
            ModelCall,
            StageSubmission,
            SessionStageEvent,
        ):
            deleted, _ = model.objects.filter(session_id__in=session_ids).delete()
            deleted_related += deleted
        deleted, _ = Message.objects.filter(
            session_id__in=session_ids,
            reply_to__isnull=False,
        ).delete()
        deleted_related += deleted
        deleted, _ = Message.objects.filter(session_id__in=session_ids).delete()
        deleted_related += deleted
        deleted_sessions, _ = SimulationSession.objects.filter(id__in=session_ids).delete()

    return RetentionResult(
        materialized_expirations=materialized,
        deleted_sessions=deleted_sessions,
        deleted_related_records=deleted_related,
    )
