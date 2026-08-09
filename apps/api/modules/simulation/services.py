import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from modules.accounts.models import RoleCode
from modules.cases.models import DisclosureMode, PhysicalExam, VersionStatus
from modules.cases.services import effective_patient_prompt, effective_patient_questions

from .gateways import (
    PATIENT_ANSWER_PROMPT_VERSION,
    PATIENT_INITIATIVE_QUESTION_PROMPT_VERSION,
    PATIENT_INITIATIVE_RESPONSE_PROMPT_VERSION,
    PATIENT_ROUTE_PROMPT_VERSION,
    PHYSICAL_EXAM_INTENT,
    GatewayError,
    GatewayResult,
    InitiativeResponseResult,
    PatientFact,
    PatientGateway,
    RoutingResult,
    answer_repeats_written_fact,
    get_patient_gateway,
    initiative_request_hash,
    request_hash,
    spoken_patient_fallback,
)
from .models import (
    AIEvaluationRun,
    AIEvaluationStatus,
    AssignmentStatus,
    AssignmentStudent,
    CaseAssignment,
    Message,
    MessageKind,
    MessageRole,
    ModelCall,
    ModelCallStatus,
    PatientInitiativeSchedule,
    PatientQuestionAttempt,
    PatientQuestionAttemptKind,
    PatientQuestionAttemptOutcome,
    PatientQuestionState,
    PatientQuestionStatus,
    PhysicalExamRelease,
    ResponseStatus,
    SessionStage,
    SessionStageEvent,
    SessionStatus,
    SimulationSession,
    StageSubmission,
    SubmissionType,
)
from .reviews import (
    ai_results_by_code,
    effective_decision,
    effective_score,
    latest_ai_run,
    latest_review,
    review_overrides,
    score_summary,
    unresolved_issues,
)
from .scoring import generate_assessment

RETENTION_DAYS = 180
PATIENT_INITIATIVE_IDLE_SECONDS = 30
PATIENT_INITIATIVE_CLAIM_SECONDS = 45


class SimulationError(Exception):
    code = "simulation_error"


class AssignmentUnavailableError(SimulationError):
    code = "assignment_unavailable"


class AttemptAlreadyUsedError(SimulationError):
    code = "attempt_already_used"


class SessionExpiredError(SimulationError):
    code = "session_expired"


class SessionLockedError(SimulationError):
    code = "session_locked"


class CaseDraftConflictError(SimulationError):
    code = "case_draft_conflict"


class ModelUnavailableError(SimulationError):
    code = "model_unavailable"


class FeedbackUnavailableError(SimulationError):
    code = "feedback_unavailable"


class PatientInitiativeUnavailableError(SimulationError):
    code = "patient_initiative_unavailable"


@dataclass(frozen=True)
class StartSessionResult:
    session: SimulationSession
    created: bool


@dataclass(frozen=True)
class ExchangeResult:
    student_message: Message
    patient_message: Message | None
    reused: bool
    interaction_type: str


@dataclass(frozen=True)
class InitiativeTriggerResult:
    patient_message: Message | None
    reused: bool


def create_assignment(
    *,
    title: str,
    case_version,
    class_group,
    duration_minutes: int,
    opens_at,
    deadline_at,
    user,
) -> CaseAssignment:
    if case_version.status != VersionStatus.PUBLISHED:
        raise AssignmentUnavailableError("只能发布已经生成版本号的病例。")
    try:
        physical_exam_findings = case_version.physical_exam.findings_text
    except PhysicalExam.DoesNotExist:
        physical_exam_findings = ""
    if not physical_exam_findings.strip():
        raise AssignmentUnavailableError("该病例版本缺少口腔体格检查资料，不能发布任务。")
    if not case_version.case.is_active:
        raise AssignmentUnavailableError("该病例已经停用，不能发布新任务。")
    latest_version_id = (
        case_version.case.versions.filter(status=VersionStatus.PUBLISHED)
        .order_by("-version_number")
        .values_list("id", flat=True)
        .first()
    )
    if case_version.id != latest_version_id:
        raise AssignmentUnavailableError("只能使用该病例的最新发布版本创建任务。")
    if not class_group.is_active:
        raise AssignmentUnavailableError("该班级已经停用，不能发布新任务。")
    can_use_case = case_version.case.created_by_id == user.id
    can_manage_class = class_group.created_by_id == user.id
    elevated = user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR)
    if not elevated and not can_use_case:
        raise AssignmentUnavailableError("你没有该病例的任务发布权限。")
    if not (elevated or can_manage_class):
        raise AssignmentUnavailableError("你没有该班级的任务发布权限。")

    students = list(class_group.memberships.values_list("student_id", flat=True))
    if not students:
        raise AssignmentUnavailableError("班级中没有学生，无法发布任务。")

    with transaction.atomic():
        assignment = CaseAssignment(
            title=title,
            case_version=case_version,
            class_group=class_group,
            duration_minutes=duration_minutes,
            opens_at=opens_at,
            deadline_at=deadline_at,
            created_by=user,
        )
        assignment.full_clean()
        assignment.save()
        AssignmentStudent.objects.bulk_create(
            [
                AssignmentStudent(assignment=assignment, student_id=student_id)
                for student_id in students
            ]
        )
        return assignment


def close_assignment(*, assignment: CaseAssignment) -> CaseAssignment:
    now = timezone.now()
    with transaction.atomic():
        locked = CaseAssignment.objects.select_for_update().get(pk=assignment.pk)
        if locked.status != AssignmentStatus.CLOSED:
            locked.status = AssignmentStatus.CLOSED
            locked.save(update_fields=["status", "updated_at"])
            SimulationSession.objects.filter(
                assignment=locked,
                status=SessionStatus.ACTIVE,
            ).update(
                status=SessionStatus.EXPIRED,
                completed_at=now,
                retention_expires_at=now + timedelta(days=RETENTION_DAYS),
                updated_at=now,
            )
            Message.objects.filter(
                session__assignment=locked,
                role=MessageRole.STUDENT,
                response_status=ResponseStatus.PROCESSING,
            ).update(
                response_status=ResponseStatus.FAILED,
                error_code="assignment_closed",
            )
    for session in SimulationSession.objects.filter(assignment=locked):
        generate_assessment(session)
    return locked


def release_feedback(*, assignment: CaseAssignment) -> CaseAssignment:
    current = CaseAssignment.objects.get(pk=assignment.pk)
    if current.status != AssignmentStatus.CLOSED:
        raise FeedbackUnavailableError("必须先结束任务，才能统一发布反馈。")
    for session in SimulationSession.objects.filter(assignment=current):
        generate_assessment(session)
    with transaction.atomic():
        locked = CaseAssignment.objects.select_for_update().get(pk=assignment.pk)
        if locked.status != AssignmentStatus.CLOSED:
            raise FeedbackUnavailableError("必须先结束任务，才能统一发布反馈。")
        if AIEvaluationRun.objects.filter(
            session__assignment=locked,
            status=AIEvaluationStatus.RUNNING,
        ).exists():
            raise FeedbackUnavailableError("仍有 AI 评价正在生成，请完成后再发布反馈。")
        if locked.feedback_released_at is None:
            locked.feedback_released_at = timezone.now()
            locked.save(update_fields=["feedback_released_at", "updated_at"])
        return locked


def _expire_if_needed(session: SimulationSession, *, now=None) -> bool:
    now = now or timezone.now()
    if session.status == SessionStatus.ACTIVE and (
        now >= session.deadline_at or session.assignment.status == AssignmentStatus.CLOSED
    ):
        session.status = SessionStatus.EXPIRED
        session.completed_at = now
        session.retention_expires_at = now + timedelta(days=RETENTION_DAYS)
        session.save(
            update_fields=[
                "status",
                "completed_at",
                "retention_expires_at",
                "updated_at",
            ]
        )
        generate_assessment(session)
        return True
    return session.status == SessionStatus.EXPIRED


def expire_overdue_sessions(*, now=None) -> int:
    now = now or timezone.now()
    session_ids = list(
        SimulationSession.objects.filter(status=SessionStatus.ACTIVE)
        .filter(Q(deadline_at__lte=now) | Q(assignment__status=AssignmentStatus.CLOSED))
        .values_list("id", flat=True)
    )
    expired_count = 0
    for session_id in session_ids:
        with transaction.atomic():
            session = (
                SimulationSession.objects.select_for_update()
                .select_related("assignment")
                .get(pk=session_id)
            )
            was_active = session.status == SessionStatus.ACTIVE
            if _expire_if_needed(session, now=now) and was_active:
                expired_count += 1
    return expired_count


def start_session(*, assignment: CaseAssignment, student) -> StartSessionResult:
    now = timezone.now()
    with transaction.atomic():
        locked_assignment = CaseAssignment.objects.select_for_update().get(pk=assignment.pk)
        if not AssignmentStudent.objects.filter(
            assignment=locked_assignment,
            student=student,
        ).exists():
            raise AssignmentUnavailableError("你不在该任务名单中。")
        if (
            locked_assignment.status != AssignmentStatus.OPEN
            or now < locked_assignment.opens_at
            or now >= locked_assignment.deadline_at
        ):
            raise AssignmentUnavailableError("该问诊任务当前不可进入。")

        existing = SimulationSession.objects.filter(
            assignment=locked_assignment,
            student=student,
        ).first()
        if existing:
            if not _expire_if_needed(existing, now=now) and existing.status == SessionStatus.ACTIVE:
                return StartSessionResult(session=existing, created=False)
            raise AttemptAlreadyUsedError("该病例任务只允许一次作答。")

        deadline = min(
            locked_assignment.deadline_at,
            now + timedelta(minutes=locked_assignment.duration_minutes),
        )
        try:
            session = SimulationSession.objects.create(
                assignment=locked_assignment,
                student=student,
                case_version=locked_assignment.case_version,
                started_at=now,
                deadline_at=deadline,
                retention_expires_at=deadline + timedelta(days=RETENTION_DAYS),
            )
        except IntegrityError as error:
            raise AttemptAlreadyUsedError("该病例任务只允许一次作答。") from error
        SessionStageEvent.objects.create(
            session=session,
            from_stage="",
            to_stage=SessionStage.INTERVIEW,
        )
        return StartSessionResult(session=session, created=True)


def require_active_session(*, session: SimulationSession, student) -> SimulationSession:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊会话。")
    expired = False
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked):
            expired = True
        elif locked.status != SessionStatus.ACTIVE:
            raise SessionLockedError("该问诊会话已经结束。")
    if expired:
        raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
    return locked


def remaining_seconds(session: SimulationSession) -> int:
    if session.status != SessionStatus.ACTIVE:
        return 0
    return max(0, int((session.deadline_at - timezone.now()).total_seconds()))


def refresh_session_status(*, session: SimulationSession, student) -> SimulationSession:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊会话。")
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        _expire_if_needed(locked)
        return locked


def _patient_facts(session: SimulationSession) -> list[PatientFact]:
    return [
        PatientFact(
            code=fact.code,
            standard_fact=fact.standard_fact,
            patient_expression=fact.patient_expression,
            disclosure_mode=fact.disclosure_mode,
            certainty=fact.certainty,
        )
        for fact in session.case_version.facts.exclude(disclosure_mode=DisclosureMode.NEVER)
    ]


def _recent_conversation(*, session: SimulationSession, current_message: Message) -> list[dict]:
    recent = list(
        session.messages.exclude(pk=current_message.pk)
        .exclude(role=MessageRole.SYSTEM)
        .order_by("-sequence")[:12]
    )
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(recent)
    ]


def _diagnosis_leaked(session: SimulationSession, answer: str) -> bool:
    normalized = answer.casefold()
    for rule in session.case_version.diagnosis_rules.all():
        terms = [rule.name, *rule.aliases]
        if any(str(term).casefold() in normalized for term in terms if len(str(term).strip()) >= 2):
            return True
    return False


def patient_initiative_payload(session: SimulationSession) -> dict:
    configured = [
        item
        for item in effective_patient_questions(session.case_version)
        if item.get("enabled")
    ]
    enabled = bool(session.case_version.patient_questions_enabled and configured)
    schedule = PatientInitiativeSchedule.objects.filter(session=session).first()
    if schedule is None:
        return {
            "enabled": enabled,
            "phase": "inactive",
            "activated_at": None,
            "next_due_at": None,
            "active_message_id": None,
        }
    states = list(PatientQuestionState.objects.filter(session=session))
    pending = next(
        (state for state in states if state.status == PatientQuestionStatus.PENDING),
        None,
    )
    complete = bool(states) and all(
        state.status == PatientQuestionStatus.ADDRESSED for state in states
    )
    return {
        "enabled": enabled,
        "phase": (
            "complete"
            if complete
            else "awaiting_student"
            if pending
            else "idle"
        ),
        "activated_at": schedule.activated_at,
        "next_due_at": schedule.next_due_at,
        "active_message_id": (
            str(pending.current_question_message_id)
            if pending and pending.current_question_message_id
            else None
        ),
    }


def activate_patient_initiative(*, session: SimulationSession, student) -> SimulationSession:
    require_active_session(session=session, student=student)
    if not PhysicalExamRelease.objects.filter(session=session).exists():
        raise PatientInitiativeUnavailableError("完成并关闭首次体格检查后才能激活患者主动提问。")
    configured = [
        dict(item)
        for item in effective_patient_questions(session.case_version)
        if item.get("enabled")
    ]
    if not session.case_version.patient_questions_enabled or not configured:
        return session
    now = timezone.now()
    with transaction.atomic():
        locked = (
            SimulationSession.objects.select_for_update()
            .select_related("assignment", "case_version")
            .get(pk=session.pk)
        )
        if _expire_if_needed(locked, now=now):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        schedule, created = PatientInitiativeSchedule.objects.get_or_create(
            session=locked,
            defaults={
                "activated_at": now,
                "next_due_at": now + timedelta(seconds=PATIENT_INITIATIVE_IDLE_SECONDS),
            },
        )
        if created:
            PatientQuestionState.objects.bulk_create(
                [
                    PatientQuestionState(
                        session=locked,
                        question_id=str(item["id"]),
                        base_question=str(item["base_question"]),
                        answer_criteria=str(item["answer_criteria"]),
                    )
                    for item in configured
                ]
            )
        return locked


def _patient_profile_payload(session: SimulationSession) -> dict:
    profile = session.case_version.patient_profile
    return {
        "age": profile.age,
        "sex": profile.sex,
        "occupation": profile.occupation,
        "education": profile.education,
        "personality": profile.personality,
        "emotion": profile.emotion,
        "cooperation": profile.cooperation,
        "medical_literacy": profile.medical_literacy,
    }


def _claim_due_patient_question(*, session: SimulationSession, now) -> dict | None:
    with transaction.atomic():
        locked_session = (
            SimulationSession.objects.select_for_update()
            .select_related("assignment", "case_version", "case_version__patient_profile")
            .get(pk=session.pk)
        )
        if _expire_if_needed(locked_session, now=now):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        if locked_session.status != SessionStatus.ACTIVE:
            raise SessionLockedError("该问诊会话已经结束。")
        schedule = PatientInitiativeSchedule.objects.select_for_update().filter(
            session=locked_session
        ).first()
        if schedule is None:
            raise PatientInitiativeUnavailableError("患者主动提问尚未激活。")
        if schedule.generation_token:
            claim_expired = bool(
                schedule.generation_started_at is None
                or schedule.generation_started_at
                <= now - timedelta(seconds=PATIENT_INITIATIVE_CLAIM_SECONDS)
            )
            if not claim_expired:
                return None
            schedule.generation_token = ""
            schedule.generation_started_at = None
            schedule.next_due_at = schedule.next_due_at or now
            schedule.save(
                update_fields=[
                    "generation_token",
                    "generation_started_at",
                    "next_due_at",
                    "updated_at",
                ]
            )
        if schedule.next_due_at is None or schedule.next_due_at > now:
            return None
        if Message.objects.filter(
            session=locked_session,
            role=MessageRole.STUDENT,
            response_status=ResponseStatus.PROCESSING,
        ).exists():
            return None

        pending = PatientQuestionState.objects.select_for_update().filter(
            session=locked_session,
            status=PatientQuestionStatus.PENDING,
        ).first()
        previous_attempt_id = None
        reminder = False
        if pending:
            previous_attempt = pending.attempts.filter(
                outcome=PatientQuestionAttemptOutcome.PENDING
            ).order_by("-created_at").first()
            if pending.reminder_count >= 1:
                if previous_attempt:
                    previous_attempt.outcome = PatientQuestionAttemptOutcome.SILENT
                    previous_attempt.evaluated_at = now
                    previous_attempt.reason = "患者提醒后 30 秒仍未收到学生回应。"
                    previous_attempt.save(
                        update_fields=["outcome", "evaluated_at", "reason"]
                    )
                pending.status = PatientQuestionStatus.DEFERRED
                pending.reminder_count = 0
                pending.current_question_message = None
                pending.eligible_at = now + timedelta(
                    seconds=PATIENT_INITIATIVE_IDLE_SECONDS
                )
                pending.save(
                    update_fields=[
                        "status",
                        "reminder_count",
                        "current_question_message",
                        "eligible_at",
                        "updated_at",
                    ]
                )
                schedule.next_due_at = pending.eligible_at
                schedule.generation_token = ""
                schedule.generation_started_at = None
                schedule.save(
                    update_fields=[
                        "next_due_at",
                        "generation_token",
                        "generation_started_at",
                        "updated_at",
                    ]
                )
                return None
            reminder = True
            state = pending
            previous_attempt_id = previous_attempt.id if previous_attempt else None
        else:
            unasked = list(
                PatientQuestionState.objects.select_for_update().filter(
                    session=locked_session,
                    status=PatientQuestionStatus.UNASKED,
                )
            )
            candidates = unasked
            if not candidates:
                candidates = list(
                    PatientQuestionState.objects.select_for_update().filter(
                        session=locked_session,
                        status=PatientQuestionStatus.DEFERRED,
                    ).filter(Q(eligible_at__isnull=True) | Q(eligible_at__lte=now))
                )
            if not candidates:
                incomplete = PatientQuestionState.objects.filter(
                    session=locked_session
                ).exclude(status=PatientQuestionStatus.ADDRESSED)
                if not incomplete.exists():
                    schedule.next_due_at = None
                    schedule.save(update_fields=["next_due_at", "updated_at"])
                else:
                    earliest = incomplete.order_by("eligible_at").values_list(
                        "eligible_at", flat=True
                    ).first()
                    schedule.next_due_at = earliest or (
                        now + timedelta(seconds=PATIENT_INITIATIVE_IDLE_SECONDS)
                    )
                    schedule.save(update_fields=["next_due_at", "updated_at"])
                return None
            state = secrets.choice(candidates)

        token = uuid.uuid4().hex
        schedule.generation_token = token
        schedule.generation_started_at = now
        schedule.generation_anchor_sequence = locked_session.last_message_sequence
        schedule.next_due_at = None
        schedule.save(
            update_fields=[
                "generation_token",
                "generation_started_at",
                "generation_anchor_sequence",
                "next_due_at",
                "updated_at",
            ]
        )
        return {
            "session": locked_session,
            "state_id": state.id,
            "token": token,
            "anchor_sequence": locked_session.last_message_sequence,
            "reminder": reminder,
            "previous_attempt_id": previous_attempt_id,
            "base_question": state.base_question,
            "patient_prompt": effective_patient_prompt(locked_session.case_version),
            "patient_profile": _patient_profile_payload(locked_session),
            "previous_phrasings": list(
                state.attempts.exclude(patient_message__isnull=True)
                .order_by("created_at")
                .values_list("patient_message__content", flat=True)
            ),
        }


def trigger_patient_initiative(
    *,
    session: SimulationSession,
    student,
    gateway: PatientGateway | None = None,
) -> InitiativeTriggerResult:
    require_active_session(session=session, student=student)
    now = timezone.now()
    claim = _claim_due_patient_question(session=session, now=now)
    if claim is None:
        pending = PatientQuestionState.objects.filter(
            session=session,
            status=PatientQuestionStatus.PENDING,
        ).select_related("current_question_message").first()
        return InitiativeTriggerResult(
            patient_message=(pending.current_question_message if pending else None),
            reused=True,
        )

    patient_gateway = gateway
    generation_error = ""
    payload = {
        "base_question": claim["base_question"],
        "patient_prompt": claim["patient_prompt"],
        "patient_profile": claim["patient_profile"],
        "previous_phrasings": claim["previous_phrasings"],
        "reminder": claim["reminder"],
    }
    try:
        patient_gateway = patient_gateway or get_patient_gateway()
        generated = patient_gateway.generate_initiative_question(**payload)
        content = generated.question
        call_status = ModelCallStatus.SUCCEEDED
    except GatewayError as error:
        generation_error = error.code
        content = claim["base_question"]
        client = getattr(patient_gateway, "client", None)
        from .gateways import InitiativeQuestionResult

        generated = InitiativeQuestionResult(
            question=content,
            provider=(
                getattr(client, "provider", "")
                or os.environ.get("LLM_PROVIDER", "unavailable")
            ),
            model=(
                getattr(client, "model", "")
                or os.environ.get("LLM_MODEL", "unavailable")
            ),
            latency_ms=1,
        )
        call_status = ModelCallStatus.FAILED

    saved_message = None
    with transaction.atomic():
        locked_session = SimulationSession.objects.select_for_update().get(pk=session.pk)
        schedule = PatientInitiativeSchedule.objects.select_for_update().get(
            session=locked_session
        )
        state = PatientQuestionState.objects.select_for_update().get(pk=claim["state_id"])
        if (
            schedule.generation_token != claim["token"]
            or locked_session.last_message_sequence != claim["anchor_sequence"]
            or locked_session.status != SessionStatus.ACTIVE
        ):
            if schedule.generation_token == claim["token"]:
                schedule.generation_token = ""
                schedule.generation_started_at = None
                schedule.save(
                    update_fields=[
                        "generation_token",
                        "generation_started_at",
                        "updated_at",
                    ]
                )
            ModelCall.objects.create(
                session=locked_session,
                provider=generated.provider,
                model=generated.model,
                prompt_version=PATIENT_INITIATIVE_QUESTION_PROMPT_VERSION,
                request_hash=initiative_request_hash(payload),
                matched_fact_codes=[],
                status=ModelCallStatus.FAILED,
                latency_ms=generated.latency_ms,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                error_code="stale_generation",
            )
            return InitiativeTriggerResult(patient_message=None, reused=True)

        locked_session.last_message_sequence += 1
        locked_session.save(update_fields=["last_message_sequence", "updated_at"])
        saved_message = Message.objects.create(
            session=locked_session,
            sequence=locked_session.last_message_sequence,
            role=MessageRole.PATIENT,
            kind=MessageKind.PATIENT_INITIATED_QUESTION,
            content=content,
        )
        if claim["previous_attempt_id"]:
            previous = PatientQuestionAttempt.objects.select_for_update().filter(
                pk=claim["previous_attempt_id"],
                outcome=PatientQuestionAttemptOutcome.PENDING,
            ).first()
            if previous:
                previous.outcome = PatientQuestionAttemptOutcome.SILENT
                previous.evaluated_at = now
                previous.reason = "患者提问后 30 秒未收到学生回应。"
                previous.save(update_fields=["outcome", "evaluated_at", "reason"])
        PatientQuestionAttempt.objects.create(
            state=state,
            kind=(
                PatientQuestionAttemptKind.REMINDER
                if claim["reminder"]
                else PatientQuestionAttemptKind.INITIAL
            ),
            patient_message=saved_message,
        )
        state.status = PatientQuestionStatus.PENDING
        state.asked_count += 1
        state.reminder_count = 1 if claim["reminder"] else 0
        state.current_question_message = saved_message
        state.eligible_at = None
        state.save(
            update_fields=[
                "status",
                "asked_count",
                "reminder_count",
                "current_question_message",
                "eligible_at",
                "updated_at",
            ]
        )
        schedule.next_due_at = saved_message.created_at + timedelta(
            seconds=PATIENT_INITIATIVE_IDLE_SECONDS
        )
        schedule.generation_token = ""
        schedule.generation_started_at = None
        schedule.save(
            update_fields=[
                "next_due_at",
                "generation_token",
                "generation_started_at",
                "updated_at",
            ]
        )
        ModelCall.objects.create(
            session=locked_session,
            patient_message=saved_message,
            provider=generated.provider,
            model=generated.model,
            prompt_version=PATIENT_INITIATIVE_QUESTION_PROMPT_VERSION,
            request_hash=initiative_request_hash(payload),
            matched_fact_codes=[],
            status=call_status,
            latency_ms=generated.latency_ms,
            input_tokens=generated.input_tokens,
            output_tokens=generated.output_tokens,
            error_code=generation_error,
        )
    return InitiativeTriggerResult(patient_message=saved_message, reused=False)


def _reschedule_patient_initiative(*, session_id, anchor_time=None) -> None:
    schedule = PatientInitiativeSchedule.objects.filter(session_id=session_id).first()
    if schedule is None:
        return
    pending = PatientQuestionState.objects.filter(
        session_id=session_id,
        status=PatientQuestionStatus.PENDING,
    ).exists()
    incomplete = PatientQuestionState.objects.filter(session_id=session_id).exclude(
        status=PatientQuestionStatus.ADDRESSED
    ).exists()
    schedule.generation_token = ""
    schedule.generation_started_at = None
    schedule.next_due_at = (
        None
        if pending or not incomplete
        else (anchor_time or timezone.now())
        + timedelta(seconds=PATIENT_INITIATIVE_IDLE_SECONDS)
    )
    schedule.save(
        update_fields=[
            "generation_token",
            "generation_started_at",
            "next_due_at",
            "updated_at",
        ]
    )


def _create_student_message(*, session: SimulationSession, content: str, client_message_id: str):
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        if locked.stage != SessionStage.INTERVIEW or locked.status != SessionStatus.ACTIVE:
            raise SessionLockedError("当前会话不允许继续向患者提问。")

        existing = Message.objects.filter(
            session=locked,
            client_message_id=client_message_id,
            role=MessageRole.STUDENT,
        ).first()
        if existing:
            return existing, True

        pending_state = (
            PatientQuestionState.objects.select_for_update()
            .filter(session=locked, status=PatientQuestionStatus.PENDING)
            .select_related("current_question_message")
            .first()
        )
        reply_to = pending_state.current_question_message if pending_state else None
        schedule = PatientInitiativeSchedule.objects.select_for_update().filter(
            session=locked
        ).first()
        if schedule:
            schedule.next_due_at = None
            schedule.generation_token = ""
            schedule.generation_started_at = None
            schedule.save(
                update_fields=[
                    "next_due_at",
                    "generation_token",
                    "generation_started_at",
                    "updated_at",
                ]
            )

        locked.last_message_sequence += 1
        locked.save(update_fields=["last_message_sequence", "updated_at"])
        try:
            message = Message.objects.create(
                session=locked,
                sequence=locked.last_message_sequence,
                role=MessageRole.STUDENT,
                content=content,
                client_message_id=client_message_id,
                reply_to=reply_to,
                response_status=ResponseStatus.PROCESSING,
            )
        except IntegrityError:
            message = Message.objects.get(
                session=locked,
                client_message_id=client_message_id,
                role=MessageRole.STUDENT,
            )
            return message, True
        return message, False


def _save_patient_response(
    *,
    student_message: Message,
    result: GatewayResult,
    hashed_request: str,
    call_status: str,
    call_error: str = "",
) -> Message:
    with transaction.atomic():
        locked_session = SimulationSession.objects.select_for_update().get(
            pk=student_message.session_id
        )
        locked_student = Message.objects.select_for_update().get(pk=student_message.pk)
        existing = Message.objects.filter(reply_to=locked_student).first()
        if existing:
            return existing
        if (
            locked_session.status != SessionStatus.ACTIVE
            or locked_session.stage != SessionStage.INTERVIEW
        ):
            locked_student.response_status = ResponseStatus.FAILED
            locked_student.error_code = "session_ended"
            locked_student.save(update_fields=["response_status", "error_code"])
            ModelCall.objects.create(
                session=locked_session,
                student_message=locked_student,
                provider=result.provider,
                model=result.model,
                prompt_version=PATIENT_ANSWER_PROMPT_VERSION,
                request_hash=hashed_request,
                matched_fact_codes=result.fact_codes,
                status=ModelCallStatus.FAILED,
                latency_ms=result.latency_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                error_code="session_ended",
            )
            raise SessionExpiredError("会话已结束，本次患者回答未写入考试记录。")

        locked_session.last_message_sequence += 1
        locked_session.save(update_fields=["last_message_sequence", "updated_at"])
        patient_message = Message.objects.create(
            session=locked_session,
            sequence=locked_session.last_message_sequence,
            role=MessageRole.PATIENT,
            content=result.answer,
            reply_to=locked_student,
        )
        locked_student.response_status = ResponseStatus.COMPLETED
        locked_student.error_code = call_error
        locked_student.save(update_fields=["response_status", "error_code"])
        ModelCall.objects.create(
            session=locked_session,
            student_message=locked_student,
            patient_message=patient_message,
            provider=result.provider,
            model=result.model,
            prompt_version=PATIENT_ANSWER_PROMPT_VERSION,
            request_hash=hashed_request,
            matched_fact_codes=result.fact_codes,
            status=call_status,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            error_code=call_error,
        )
        _reschedule_patient_initiative(
            session_id=locked_session.id,
            anchor_time=patient_message.created_at,
        )
        return patient_message


def _save_routing_call(
    *,
    student_message: Message,
    result: RoutingResult,
    hashed_request: str,
    status: str,
    error_code: str = "",
) -> None:
    ModelCall.objects.create(
        session=student_message.session,
        student_message=student_message,
        provider=result.provider,
        model=result.model,
        prompt_version=PATIENT_ROUTE_PROMPT_VERSION,
        request_hash=hashed_request,
        matched_fact_codes=result.fact_codes,
        routed_intent=result.intent,
        route_confidence=result.confidence,
        status=status,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        error_code=error_code,
    )


def _existing_interaction_type(student_message: Message) -> str:
    release = PhysicalExamRelease.objects.filter(session=student_message.session).first()
    if release and release.trigger_message_id == student_message.id:
        return "physical_exam_released"
    reply = Message.objects.filter(reply_to=student_message).first()
    if reply and reply.kind == MessageKind.PHYSICAL_EXAM_CONSENT:
        return "physical_exam_reopened"
    if ModelCall.objects.filter(
        student_message=student_message,
        prompt_version=PATIENT_INITIATIVE_RESPONSE_PROMPT_VERSION,
        routed_intent=PHYSICAL_EXAM_INTENT,
    ).exists():
        return "physical_exam_reopened"
    if reply and reply.kind in (
        MessageKind.PATIENT_INITIATED_QUESTION,
        MessageKind.PATIENT_REACTION,
    ):
        return "patient_initiative_response"
    return "patient_answer"


def _save_physical_exam_response(
    *,
    student_message: Message,
) -> tuple[Message, str]:
    with transaction.atomic():
        locked_session = SimulationSession.objects.select_for_update().get(
            pk=student_message.session_id
        )
        locked_student = Message.objects.select_for_update().get(pk=student_message.pk)
        existing = Message.objects.filter(reply_to=locked_student).first()
        if existing:
            return existing, _existing_interaction_type(locked_student)
        if (
            locked_session.status != SessionStatus.ACTIVE
            or locked_session.stage != SessionStage.INTERVIEW
        ):
            locked_student.response_status = ResponseStatus.FAILED
            locked_student.error_code = "session_ended"
            locked_student.save(update_fields=["response_status", "error_code"])
            raise SessionExpiredError("会话已结束，本次体格检查请求未写入考试记录。")

        release = PhysicalExamRelease.objects.filter(session=locked_session).first()
        physical_exam = PhysicalExam.objects.get(version=locked_session.case_version)
        locked_session.last_message_sequence += 1
        consent_message = Message.objects.create(
            session=locked_session,
            sequence=locked_session.last_message_sequence,
            role=MessageRole.PATIENT,
            kind=MessageKind.PHYSICAL_EXAM_CONSENT,
            content=(
                "刚才已经检查过了，您可以再查看检查结果。"
                if release
                else physical_exam.consent_text
            ),
            reply_to=locked_student,
        )
        interaction_type = "physical_exam_reopened"
        if release is None:
            locked_session.last_message_sequence += 1
            result_message = Message.objects.create(
                session=locked_session,
                sequence=locked_session.last_message_sequence,
                role=MessageRole.SYSTEM,
                kind=MessageKind.PHYSICAL_EXAM_RESULT,
                content=physical_exam.findings_text,
            )
            PhysicalExamRelease.objects.create(
                session=locked_session,
                trigger_message=locked_student,
                consent_message=consent_message,
                result_message=result_message,
            )
            interaction_type = "physical_exam_released"
        locked_session.save(update_fields=["last_message_sequence", "updated_at"])
        locked_student.response_status = ResponseStatus.COMPLETED
        locked_student.error_code = ""
        locked_student.save(update_fields=["response_status", "error_code"])
        _reschedule_patient_initiative(
            session_id=locked_session.id,
            anchor_time=consent_message.created_at,
        )
        return consent_message, interaction_type


def _pending_initiative_attempt(student_message: Message):
    if not student_message.reply_to_id:
        return None
    return (
        PatientQuestionAttempt.objects.filter(
            patient_message_id=student_message.reply_to_id,
            outcome=PatientQuestionAttemptOutcome.PENDING,
            state__status=PatientQuestionStatus.PENDING,
        )
        .select_related("state", "patient_message")
        .first()
    )


def _initiative_gateway_failure(
    *,
    student_message: Message,
    gateway,
    prompt_version: str,
    hashed_request: str,
    error: GatewayError,
) -> None:
    student_message.response_status = ResponseStatus.FAILED
    student_message.error_code = error.code
    student_message.save(update_fields=["response_status", "error_code"])
    client = getattr(gateway, "client", None)
    ModelCall.objects.create(
        session=student_message.session,
        student_message=student_message,
        provider=(
            getattr(client, "provider", "")
            or os.environ.get("LLM_PROVIDER", "unavailable")
        ),
        model=(
            getattr(client, "model", "")
            or os.environ.get("LLM_MODEL", "unavailable")
        ),
        prompt_version=prompt_version,
        request_hash=hashed_request,
        matched_fact_codes=[],
        status=ModelCallStatus.FAILED,
        error_code=error.code,
    )
    schedule = PatientInitiativeSchedule.objects.filter(
        session=student_message.session
    ).first()
    if schedule:
        schedule.next_due_at = timezone.now() + timedelta(
            seconds=PATIENT_INITIATIVE_IDLE_SECONDS
        )
        schedule.save(update_fields=["next_due_at", "updated_at"])


def _handle_initiative_response(
    *,
    session: SimulationSession,
    student_message: Message,
    attempt: PatientQuestionAttempt,
    gateway: PatientGateway | None,
) -> ExchangeResult:
    facts = _patient_facts(session)
    history = _recent_conversation(session=session, current_message=student_message)
    fact_by_code = {fact.code: fact for fact in facts}
    patient_gateway = gateway
    try:
        physical_exam_available = bool(
            session.case_version.physical_exam.findings_text.strip()
        )
    except PhysicalExam.DoesNotExist:
        physical_exam_available = False
    evaluation_payload = {
        "patient_question": attempt.patient_message.content,
        "answer_criteria": attempt.state.answer_criteria,
        "student_message": student_message.content,
        "history": history,
        "fact_codes": [fact.code for fact in facts],
        "physical_exam_available": physical_exam_available,
    }
    evaluation_hash = initiative_request_hash(evaluation_payload)
    try:
        patient_gateway = patient_gateway or get_patient_gateway()
        decision: InitiativeResponseResult = patient_gateway.evaluate_initiative_response(
            patient_question=attempt.patient_message.content,
            answer_criteria=attempt.state.answer_criteria,
            student_message=student_message.content,
            facts=facts,
            history=history,
            physical_exam_available=physical_exam_available,
        )
        if not set(decision.fact_codes).issubset(fact_by_code):
            raise GatewayError(
                "主动问题回应判定返回了未知事实。",
                code="invalid_initiative_facts",
            )
        ModelCall.objects.create(
            session=session,
            student_message=student_message,
            provider=decision.provider,
            model=decision.model,
            prompt_version=PATIENT_INITIATIVE_RESPONSE_PROMPT_VERSION,
            request_hash=evaluation_hash,
            matched_fact_codes=decision.fact_codes,
            routed_intent=decision.intent,
            route_confidence=decision.confidence,
            status=ModelCallStatus.SUCCEEDED,
            latency_ms=decision.latency_ms,
            input_tokens=decision.input_tokens,
            output_tokens=decision.output_tokens,
        )
    except GatewayError as error:
        _initiative_gateway_failure(
            student_message=student_message,
            gateway=patient_gateway,
            prompt_version=PATIENT_INITIATIVE_RESPONSE_PROMPT_VERSION,
            hashed_request=evaluation_hash,
            error=error,
        )
        raise ModelUnavailableError("患者语义理解模型暂时不可用，请稍后重试。") from error

    selected_facts = [fact_by_code[code] for code in decision.fact_codes]
    suffix = ""
    answer_result = None
    answer_status = ModelCallStatus.SUCCEEDED
    answer_error = ""
    interaction_type = "patient_initiative_response"
    if decision.asks_patient_question:
        if decision.intent == PHYSICAL_EXAM_INTENT:
            suffix = "刚才已经检查过了，您可以再查看检查结果。"
            interaction_type = "physical_exam_reopened"
        elif not selected_facts:
            suffix = "这个我不太清楚。要不我们还是聊聊我这次口腔不舒服的情况吧。"
        else:
            try:
                answer_result = patient_gateway.answer(
                    question=student_message.content,
                    facts=selected_facts,
                    history=history,
                    patient_prompt=effective_patient_prompt(session.case_version),
                )
            except GatewayError as error:
                answer_hash = request_hash(
                    question=student_message.content,
                    facts=selected_facts,
                    history=history,
                    patient_prompt=effective_patient_prompt(session.case_version),
                )
                _initiative_gateway_failure(
                    student_message=student_message,
                    gateway=patient_gateway,
                    prompt_version=PATIENT_ANSWER_PROMPT_VERSION,
                    hashed_request=answer_hash,
                    error=error,
                )
                raise ModelUnavailableError("患者模型暂时不可用，请稍后重试。") from error
            allowed_codes = {fact.code for fact in selected_facts}
            invalid = (
                not answer_result.fact_codes
                or not set(answer_result.fact_codes).issubset(allowed_codes)
                or _diagnosis_leaked(session, answer_result.answer)
                or answer_repeats_written_fact(answer_result.answer, selected_facts)
            )
            if invalid:
                answer_result = GatewayResult(
                    answer=spoken_patient_fallback(
                        selected_facts,
                        question=student_message.content,
                    ),
                    fact_codes=[fact.code for fact in selected_facts],
                    provider=answer_result.provider,
                    model=answer_result.model,
                    latency_ms=answer_result.latency_ms,
                    input_tokens=answer_result.input_tokens,
                    output_tokens=answer_result.output_tokens,
                )
                answer_status = ModelCallStatus.FAILED
                answer_error = "response_validation_failed"
            suffix = answer_result.answer

    generation_result = None
    generation_error = ""
    if decision.addressed:
        prefix = "好的，我明白了。"
        next_status = PatientQuestionStatus.ADDRESSED
    elif attempt.state.reminder_count == 0:
        generation_payload = {
            "base_question": attempt.state.base_question,
            "patient_prompt": effective_patient_prompt(session.case_version),
            "patient_profile": _patient_profile_payload(session),
            "previous_phrasings": list(
                attempt.state.attempts.exclude(patient_message__isnull=True)
                .order_by("created_at")
                .values_list("patient_message__content", flat=True)
            ),
            "reminder": True,
        }
        try:
            generation_result = patient_gateway.generate_initiative_question(
                **generation_payload
            )
            prefix = generation_result.question
        except GatewayError as error:
            generation_error = error.code
            prefix = attempt.state.base_question
        next_status = PatientQuestionStatus.PENDING
    else:
        prefix = "好吧，那我们先说别的，您方便时再告诉我。"
        next_status = PatientQuestionStatus.DEFERRED

    content = prefix if not suffix else f"{prefix.rstrip()} {suffix.lstrip()}"
    now = timezone.now()
    with transaction.atomic():
        locked_session = SimulationSession.objects.select_for_update().get(pk=session.pk)
        locked_student = Message.objects.select_for_update().get(pk=student_message.pk)
        locked_attempt = (
            PatientQuestionAttempt.objects.select_for_update()
            .select_related("state")
            .get(pk=attempt.pk)
        )
        existing = Message.objects.filter(reply_to=locked_student).first()
        if existing:
            return ExchangeResult(
                locked_student,
                existing,
                True,
                _existing_interaction_type(locked_student),
            )
        if (
            locked_session.status != SessionStatus.ACTIVE
            or locked_attempt.outcome != PatientQuestionAttemptOutcome.PENDING
        ):
            locked_student.response_status = ResponseStatus.FAILED
            locked_student.error_code = "session_ended"
            locked_student.save(update_fields=["response_status", "error_code"])
            raise SessionExpiredError("会话已结束，本次患者回答未写入考试记录。")

        locked_session.last_message_sequence += 1
        locked_session.save(update_fields=["last_message_sequence", "updated_at"])
        patient_message = Message.objects.create(
            session=locked_session,
            sequence=locked_session.last_message_sequence,
            role=MessageRole.PATIENT,
            kind=(
                MessageKind.PATIENT_INITIATED_QUESTION
                if next_status == PatientQuestionStatus.PENDING
                else MessageKind.PATIENT_REACTION
            ),
            content=content,
            reply_to=locked_student,
        )
        locked_student.response_status = ResponseStatus.COMPLETED
        locked_student.error_code = answer_error
        locked_student.save(update_fields=["response_status", "error_code"])
        locked_attempt.student_message = locked_student
        locked_attempt.reaction_message = patient_message
        locked_attempt.outcome = (
            PatientQuestionAttemptOutcome.ADDRESSED
            if decision.addressed
            else PatientQuestionAttemptOutcome.EVADED
        )
        locked_attempt.confidence = decision.confidence
        locked_attempt.reason = decision.reason
        locked_attempt.evaluated_at = now
        locked_attempt.save(
            update_fields=[
                "student_message",
                "reaction_message",
                "outcome",
                "confidence",
                "reason",
                "evaluated_at",
            ]
        )
        state = PatientQuestionState.objects.select_for_update().get(
            pk=locked_attempt.state_id
        )
        state.status = next_status
        state.last_decision_confidence = decision.confidence
        state.last_decision_reason = decision.reason
        schedule = PatientInitiativeSchedule.objects.select_for_update().get(
            session=locked_session
        )
        if next_status == PatientQuestionStatus.ADDRESSED:
            state.current_question_message = None
            state.addressed_by_message = locked_student
            state.addressed_at = now
            state.reminder_count = 0
            state.eligible_at = None
            remaining = PatientQuestionState.objects.filter(session=locked_session).exclude(
                pk=state.pk
            ).exclude(status=PatientQuestionStatus.ADDRESSED).exists()
            schedule.next_due_at = (
                patient_message.created_at
                + timedelta(seconds=PATIENT_INITIATIVE_IDLE_SECONDS)
                if remaining
                else None
            )
        elif next_status == PatientQuestionStatus.PENDING:
            state.current_question_message = patient_message
            state.reminder_count = 1
            state.eligible_at = None
            PatientQuestionAttempt.objects.create(
                state=state,
                kind=PatientQuestionAttemptKind.REMINDER,
                patient_message=patient_message,
            )
            schedule.next_due_at = patient_message.created_at + timedelta(
                seconds=PATIENT_INITIATIVE_IDLE_SECONDS
            )
        else:
            state.current_question_message = None
            state.reminder_count = 0
            state.eligible_at = patient_message.created_at + timedelta(
                seconds=PATIENT_INITIATIVE_IDLE_SECONDS
            )
            schedule.next_due_at = state.eligible_at
        state.save(
            update_fields=[
                "status",
                "current_question_message",
                "addressed_by_message",
                "addressed_at",
                "reminder_count",
                "eligible_at",
                "last_decision_confidence",
                "last_decision_reason",
                "updated_at",
            ]
        )
        schedule.generation_token = ""
        schedule.generation_started_at = None
        schedule.save(
            update_fields=[
                "next_due_at",
                "generation_token",
                "generation_started_at",
                "updated_at",
            ]
        )
        if answer_result is not None:
            ModelCall.objects.create(
                session=locked_session,
                student_message=locked_student,
                patient_message=patient_message,
                provider=answer_result.provider,
                model=answer_result.model,
                prompt_version=PATIENT_ANSWER_PROMPT_VERSION,
                request_hash=request_hash(
                    question=locked_student.content,
                    facts=selected_facts,
                    history=history,
                    patient_prompt=effective_patient_prompt(session.case_version),
                ),
                matched_fact_codes=answer_result.fact_codes,
                status=answer_status,
                latency_ms=answer_result.latency_ms,
                input_tokens=answer_result.input_tokens,
                output_tokens=answer_result.output_tokens,
                error_code=answer_error,
            )
        if generation_result is not None or generation_error:
            ModelCall.objects.create(
                session=locked_session,
                student_message=locked_student,
                patient_message=patient_message,
                provider=(
                    generation_result.provider
                    if generation_result
                    else os.environ.get("LLM_PROVIDER", "unavailable")
                ),
                model=(
                    generation_result.model
                    if generation_result
                    else os.environ.get("LLM_MODEL", "unavailable")
                ),
                prompt_version=PATIENT_INITIATIVE_QUESTION_PROMPT_VERSION,
                request_hash=initiative_request_hash(generation_payload),
                matched_fact_codes=[],
                status=(
                    ModelCallStatus.SUCCEEDED
                    if generation_result
                    else ModelCallStatus.FAILED
                ),
                latency_ms=generation_result.latency_ms if generation_result else 1,
                input_tokens=(generation_result.input_tokens if generation_result else None),
                output_tokens=(generation_result.output_tokens if generation_result else None),
                error_code=generation_error,
            )
    return ExchangeResult(
        student_message,
        patient_message,
        False,
        interaction_type,
    )


def ask_patient(
    *,
    session: SimulationSession,
    student,
    content: str,
    client_message_id: str,
    gateway: PatientGateway | None = None,
) -> ExchangeResult:
    require_active_session(session=session, student=student)
    student_message, reused = _create_student_message(
        session=session,
        content=content.strip(),
        client_message_id=client_message_id,
    )
    existing_reply = Message.objects.filter(reply_to=student_message).first()
    if existing_reply:
        return ExchangeResult(
            student_message,
            existing_reply,
            reused=True,
            interaction_type=_existing_interaction_type(student_message),
        )
    if reused and student_message.response_status == ResponseStatus.PROCESSING:
        return ExchangeResult(
            student_message,
            None,
            reused=True,
            interaction_type="patient_answer",
        )

    initiative_attempt = _pending_initiative_attempt(student_message)
    if initiative_attempt:
        return _handle_initiative_response(
            session=session,
            student_message=student_message,
            attempt=initiative_attempt,
            gateway=gateway,
        )

    facts = _patient_facts(session)
    history = _recent_conversation(session=session, current_message=student_message)
    patient_gateway = gateway
    try:
        physical_exam_available = bool(
            session.case_version.physical_exam.findings_text.strip()
        )
    except PhysicalExam.DoesNotExist:
        physical_exam_available = False
    route_hash = request_hash(
        question=content,
        facts=facts,
        history=history,
        physical_exam_available=physical_exam_available,
    )
    fact_by_code = {fact.code: fact for fact in facts}
    try:
        patient_gateway = patient_gateway or get_patient_gateway()
        route = patient_gateway.route(
            question=content,
            facts=facts,
            history=history,
            physical_exam_available=physical_exam_available,
        )
        if not set(route.fact_codes).issubset(fact_by_code):
            raise GatewayError(
                "患者语义路由返回了未知事实。",
                code="invalid_route_facts",
            )
        _save_routing_call(
            student_message=student_message,
            result=route,
            hashed_request=route_hash,
            status=ModelCallStatus.SUCCEEDED,
        )
    except GatewayError as error:
        student_message.response_status = ResponseStatus.FAILED
        student_message.error_code = error.code
        student_message.save(update_fields=["response_status", "error_code"])
        client = getattr(patient_gateway, "client", None)
        ModelCall.objects.create(
            session=session,
            student_message=student_message,
            provider=(
                getattr(client, "provider", "")
                or os.environ.get("LLM_PROVIDER", "unavailable")
            ),
            model=(
                getattr(client, "model", "") or os.environ.get("LLM_MODEL", "unavailable")
            ),
            prompt_version=PATIENT_ROUTE_PROMPT_VERSION,
            request_hash=route_hash,
            matched_fact_codes=[],
            status=ModelCallStatus.FAILED,
            error_code=error.code,
        )
        _reschedule_patient_initiative(
            session_id=session.id,
            anchor_time=timezone.now(),
        )
        raise ModelUnavailableError("患者语义理解模型暂时不可用，请稍后重试。") from error

    if route.intent == PHYSICAL_EXAM_INTENT and route.confidence >= 0.75:
        patient_message, interaction_type = _save_physical_exam_response(
            student_message=student_message,
        )
        return ExchangeResult(
            student_message,
            patient_message,
            reused,
            interaction_type,
        )

    selected_facts = [fact_by_code[code] for code in route.fact_codes]
    if not selected_facts:
        result = GatewayResult(
            answer="这个我不太清楚。要不我们还是聊聊我这次口腔不舒服的情况吧。",
            fact_codes=[],
            provider="rules",
            model="unknown-fact-policy-v2",
            latency_ms=1,
        )
        patient_message = _save_patient_response(
            student_message=student_message,
            result=result,
            hashed_request=request_hash(question=content, facts=[], history=history),
            call_status=ModelCallStatus.SUCCEEDED,
        )
        return ExchangeResult(
            student_message,
            patient_message,
            reused,
            "patient_answer",
        )

    patient_prompt = effective_patient_prompt(session.case_version)
    try:
        result = patient_gateway.answer(
            question=content,
            facts=selected_facts,
            history=history,
            patient_prompt=patient_prompt,
        )
    except GatewayError as error:
        student_message.response_status = ResponseStatus.FAILED
        student_message.error_code = error.code
        student_message.save(update_fields=["response_status", "error_code"])
        client = getattr(patient_gateway, "client", None)
        ModelCall.objects.create(
            session=session,
            student_message=student_message,
            provider=(
                getattr(client, "provider", "")
                or os.environ.get("LLM_PROVIDER", "unavailable")
            ),
            model=(
                getattr(client, "model", "") or os.environ.get("LLM_MODEL", "unavailable")
            ),
            prompt_version=PATIENT_ANSWER_PROMPT_VERSION,
            request_hash=request_hash(
                question=content,
                facts=selected_facts,
                history=history,
                patient_prompt=patient_prompt,
            ),
            matched_fact_codes=[fact.code for fact in selected_facts],
            status=ModelCallStatus.FAILED,
            error_code=error.code,
        )
        _reschedule_patient_initiative(
            session_id=session.id,
            anchor_time=timezone.now(),
        )
        raise ModelUnavailableError("患者模型暂时不可用，请稍后重试。") from error

    allowed_codes = {fact.code for fact in selected_facts}
    response_not_conversational = answer_repeats_written_fact(result.answer, selected_facts)
    response_validation_failed = (
        not result.fact_codes
        or not set(result.fact_codes).issubset(allowed_codes)
        or _diagnosis_leaked(session, result.answer)
    )
    invalid = response_validation_failed or response_not_conversational
    if invalid:
        result = GatewayResult(
            answer=spoken_patient_fallback(selected_facts, question=content),
            fact_codes=[fact.code for fact in selected_facts],
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        call_status = ModelCallStatus.FAILED
        call_error = (
            "response_validation_failed"
            if response_validation_failed
            else "response_not_conversational"
        )
    else:
        call_status = ModelCallStatus.SUCCEEDED
        call_error = ""

    patient_message = _save_patient_response(
        student_message=student_message,
        result=result,
        hashed_request=request_hash(
            question=content,
            facts=selected_facts,
            history=history,
            patient_prompt=patient_prompt,
        ),
        call_status=call_status,
        call_error=call_error,
    )
    return ExchangeResult(student_message, patient_message, reused, "patient_answer")


def save_case_draft(
    *,
    session: SimulationSession,
    student,
    case_draft: dict,
    expected_revision: int,
) -> SimulationSession:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊会话。")
    now = timezone.now()
    expired = False
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked, now=now):
            expired = True
        elif locked.status != SessionStatus.ACTIVE or locked.stage != SessionStage.INTERVIEW:
            raise SessionLockedError("该问诊会话已经结束。")
        elif locked.case_draft_revision != expected_revision:
            raise CaseDraftConflictError("病例草稿已在其他页面更新，请刷新后继续编辑。")
        else:
            locked.case_draft = case_draft
            locked.case_draft_revision += 1
            locked.save(update_fields=["case_draft", "case_draft_revision", "updated_at"])
    if expired:
        raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
    return locked


@dataclass(frozen=True)
class CompleteSessionResult:
    session: SimulationSession
    submission: StageSubmission
    reused: bool


def complete_session(
    *,
    session: SimulationSession,
    student,
    case_record: dict,
    expected_revision: int,
) -> CompleteSessionResult:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊会话。")
    now = timezone.now()
    expired = False
    with transaction.atomic():
        locked = (
            SimulationSession.objects.select_for_update()
            .select_related("assignment", "case_version")
            .get(pk=session.pk)
        )
        existing = StageSubmission.objects.filter(
            session=locked,
            submission_type=SubmissionType.CASE_RECORD,
        ).first()
        if locked.status == SessionStatus.COMPLETED and existing:
            return CompleteSessionResult(locked, existing, True)
        if _expire_if_needed(locked, now=now):
            expired = True
        elif locked.status != SessionStatus.ACTIVE or locked.stage != SessionStage.INTERVIEW:
            raise SessionLockedError("该问诊会话已经结束。")
        elif locked.case_draft_revision != expected_revision:
            raise CaseDraftConflictError("病例草稿已在其他页面更新，请刷新后继续编辑。")
        elif Message.objects.filter(
            session=locked,
            role=MessageRole.STUDENT,
            response_status=ResponseStatus.PROCESSING,
        ).exists():
            raise SessionLockedError("仍有患者回答正在生成，请等待回答完成后再交卷。")
        else:
            specialty_exam = ""
            if PhysicalExamRelease.objects.filter(session=locked).exists():
                try:
                    specialty_exam = PhysicalExam.objects.get(
                        version=locked.case_version
                    ).findings_text
                except PhysicalExam.DoesNotExist:
                    specialty_exam = ""
            final_record = {**case_record, "specialty_exam": specialty_exam}
            submission = StageSubmission.objects.create(
                session=locked,
                submission_type=SubmissionType.CASE_RECORD,
                payload=final_record,
            )
            locked.case_draft = case_record
            locked.case_draft_revision += 1
            locked.stage = SessionStage.COMPLETED
            locked.status = SessionStatus.COMPLETED
            locked.completed_at = now
            locked.retention_expires_at = now + timedelta(days=RETENTION_DAYS)
            locked.save(
                update_fields=[
                    "case_draft",
                    "case_draft_revision",
                    "stage",
                    "status",
                    "completed_at",
                    "retention_expires_at",
                    "updated_at",
                ]
            )
            SessionStageEvent.objects.create(
                session=locked,
                from_stage=SessionStage.INTERVIEW,
                to_stage=SessionStage.COMPLETED,
            )
    if expired:
        raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
    generate_assessment(locked)
    return CompleteSessionResult(locked, submission, False)


def feedback_for_session(*, session: SimulationSession, student) -> dict:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊反馈。")
    if session.assignment.feedback_released_at is None:
        raise FeedbackUnavailableError("教师尚未统一发布反馈。")
    assessment = generate_assessment(session)
    visible_results = list(session.score_results.filter(is_student_visible=True))
    review = latest_review(session)
    ai_run = latest_ai_run(session)
    ai_results = ai_results_by_code(ai_run)
    overrides = review_overrides(review)
    effective_by_code = {
        result.code: effective_score(
            result,
            review,
            ai_run=ai_run,
            ai_results=ai_results,
        )
        for result in visible_results
    }
    visible_omissions = unresolved_issues(
        session,
        assessment.omissions,
        review=review,
        student_visible_only=True,
    )
    visible_errors = unresolved_issues(
        session,
        assessment.errors,
        review=review,
        student_visible_only=True,
    )
    return {
        "session_id": str(session.id),
        "standard_diagnoses": [
            {
                "type": rule.diagnosis_type,
                "name": rule.name,
                "supporting_evidence": rule.supporting_evidence,
            }
            for rule in session.case_version.diagnosis_rules.all()
        ],
        "standard_tests": [
            {
                "code": test.code,
                "name": test.name,
                "result": test.result_text,
                "interpretation": test.teacher_interpretation,
            }
            for test in session.case_version.tests.all()
        ],
        "score": score_summary(
            session,
            student_visible_only=True,
            review=review,
        ),
        "scoring_items": [
            {
                "code": result.code,
                "label": result.label,
                "dimension": result.dimension,
                "evaluation_method": result.evaluation_method,
                "automatic_score": (
                    float(result.automatic_score)
                    if result.automatic_score is not None
                    else None
                ),
                "teacher_score": (
                    float(overrides[result.code]["score"])
                    if result.code in overrides
                    and overrides[result.code].get("score") not in (None, "")
                    else None
                ),
                "ai_score": (
                    float(ai_results[result.code].score)
                    if result.code in ai_results
                    else None
                ),
                "ai_confidence": (
                    float(ai_results[result.code].confidence)
                    if result.code in ai_results
                    else None
                ),
                "ai_reason": (
                    ai_results[result.code].reason if result.code in ai_results else ""
                ),
                "ai_feedback": (
                    ai_results[result.code].feedback if result.code in ai_results else ""
                ),
                "ai_evidence_excerpt": (
                    ai_results[result.code].evidence_excerpt
                    if result.code in ai_results
                    else ""
                ),
                "effective_score": (
                    float(effective_by_code[result.code])
                    if effective_by_code[result.code] is not None
                    else None
                ),
                "adjustment_reason": (
                    str(overrides[result.code].get("reason", ""))
                    if result.code in overrides
                    else ""
                ),
                "max_score": float(result.max_score),
                "decision": result.decision,
                "effective_decision": effective_decision(
                    result,
                    review,
                    ai_run=ai_run,
                    ai_results=ai_results,
                ),
                "reason": result.reason,
                "evidence_excerpt": result.evidence_excerpt,
                "standard_answer": result.standard_answer,
            }
            for result in visible_results
        ],
        "omissions": visible_omissions,
        "errors": visible_errors,
        "feedback_summary": (
            f"当前反馈包含 {len(visible_results)} 个可见评分项；"
            f"发现 {len(visible_omissions)} 个遗漏项和 "
            f"{len(visible_errors)} 个需关注项。"
        ),
        "ai_feedback": (
            ai_run.feedback_summary
            if ai_run and any(result.code in ai_results for result in visible_results)
            else None
        ),
        "teacher_comment": review.comment if review else "",
    }
