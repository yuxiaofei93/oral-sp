from dataclasses import dataclass
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from modules.accounts.models import RoleCode
from modules.cases.models import DisclosureMode, VersionStatus
from modules.teaching.models import CourseTeacher

from .gateways import (
    GatewayError,
    GatewayResult,
    PatientFact,
    PatientGateway,
    get_patient_gateway,
    request_hash,
)
from .models import (
    AssignmentStatus,
    AssignmentStudent,
    CaseAssignment,
    Message,
    MessageRole,
    ModelCall,
    ModelCallStatus,
    ResponseStatus,
    SessionStage,
    SessionStageEvent,
    SessionStatus,
    SimulationSession,
    StageSubmission,
    SubmissionType,
)
from .reviews import (
    effective_decision,
    effective_score,
    latest_review,
    review_overrides,
    score_summary,
    unresolved_issues,
)
from .scoring import generate_assessment

RETENTION_DAYS = 180


class SimulationError(Exception):
    code = "simulation_error"


class AssignmentUnavailableError(SimulationError):
    code = "assignment_unavailable"


class AttemptAlreadyUsedError(SimulationError):
    code = "attempt_already_used"


class SessionExpiredError(SimulationError):
    code = "session_expired"


class StageLockedError(SimulationError):
    code = "stage_locked"


class DuplicateSubmissionError(SimulationError):
    code = "duplicate_submission"


class ModelUnavailableError(SimulationError):
    code = "model_unavailable"


class FeedbackUnavailableError(SimulationError):
    code = "feedback_unavailable"


@dataclass(frozen=True)
class StartSessionResult:
    session: SimulationSession
    created: bool


@dataclass(frozen=True)
class ExchangeResult:
    student_message: Message
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
    if not case_version.case.is_active:
        raise AssignmentUnavailableError("该病例已经停用，不能发布新任务。")
    if not class_group.is_active or not class_group.course.is_active:
        raise AssignmentUnavailableError("该课程或班级已经停用，不能发布新任务。")
    can_use_case = case_version.case.created_by_id == user.id
    can_manage_course = CourseTeacher.objects.filter(
        course=class_group.course,
        teacher=user,
    ).exists()
    elevated = user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR)
    if not elevated and not can_use_case:
        raise AssignmentUnavailableError("你没有该病例的任务发布权限。")
    if not (elevated or can_manage_course):
        raise AssignmentUnavailableError("你没有该课程的任务发布权限。")

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
            ).update(status=SessionStatus.EXPIRED, completed_at=now, updated_at=now)
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
        raise FeedbackUnavailableError("必须先收卷，才能统一发布反馈。")
    for session in SimulationSession.objects.filter(assignment=current):
        generate_assessment(session)
    with transaction.atomic():
        locked = CaseAssignment.objects.select_for_update().get(pk=assignment.pk)
        if locked.status != AssignmentStatus.CLOSED:
            raise FeedbackUnavailableError("必须先收卷，才能统一发布反馈。")
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
        session.save(update_fields=["status", "completed_at", "updated_at"])
        generate_assessment(session)
        return True
    return session.status == SessionStatus.EXPIRED


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
            raise AssignmentUnavailableError("该考试任务当前不可进入。")

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
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        if locked.status != SessionStatus.ACTIVE:
            raise StageLockedError("该问诊会话已经结束。")
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


def _select_facts(session: SimulationSession, question: str):
    normalized_question = question.casefold()
    candidates = session.case_version.facts.exclude(disclosure_mode=DisclosureMode.NEVER)
    selected = []
    for fact in candidates:
        triggers = [*fact.semantic_tags, *fact.synonyms]
        if any(
            str(trigger).casefold() in normalized_question
            for trigger in triggers
            if str(trigger).strip()
        ):
            selected.append(fact)
    return selected


def _diagnosis_leaked(session: SimulationSession, answer: str) -> bool:
    normalized = answer.casefold()
    for rule in session.case_version.diagnosis_rules.all():
        terms = [rule.name, *rule.aliases]
        if any(str(term).casefold() in normalized for term in terms if len(str(term).strip()) >= 2):
            return True
    return False


def _create_student_message(*, session: SimulationSession, content: str, client_message_id: str):
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        if locked.stage != SessionStage.INTERVIEW or locked.status != SessionStatus.ACTIVE:
            raise StageLockedError("当前阶段不允许继续向患者提问。")

        existing = Message.objects.filter(
            session=locked,
            client_message_id=client_message_id,
            role=MessageRole.STUDENT,
        ).first()
        if existing:
            return existing, True

        locked.last_message_sequence += 1
        locked.save(update_fields=["last_message_sequence", "updated_at"])
        try:
            message = Message.objects.create(
                session=locked,
                sequence=locked.last_message_sequence,
                role=MessageRole.STUDENT,
                content=content,
                client_message_id=client_message_id,
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
            request_hash=hashed_request,
            matched_fact_codes=result.fact_codes,
            status=call_status,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            error_code=call_error,
        )
        return patient_message


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
        return ExchangeResult(student_message, existing_reply, reused=True)
    if reused and student_message.response_status == ResponseStatus.PROCESSING:
        return ExchangeResult(student_message, None, reused=True)

    selected = _select_facts(session, content)
    facts = [
        PatientFact(
            code=fact.code,
            patient_expression=fact.patient_expression,
            certainty=fact.certainty,
        )
        for fact in selected
    ]
    if not facts:
        unknown = selected[0].unknown_response if selected else "这个我不太清楚。"
        result = GatewayResult(
            answer=unknown,
            fact_codes=[],
            provider="rules",
            model="unknown-fact-policy-v1",
            latency_ms=1,
        )
        patient_message = _save_patient_response(
            student_message=student_message,
            result=result,
            hashed_request=request_hash(question=content, facts=[]),
            call_status=ModelCallStatus.SUCCEEDED,
        )
        return ExchangeResult(student_message, patient_message, reused)

    try:
        patient_gateway = gateway or get_patient_gateway()
        result = patient_gateway.answer(question=content, facts=facts)
    except GatewayError as error:
        student_message.response_status = ResponseStatus.FAILED
        student_message.error_code = "gateway_error"
        student_message.save(update_fields=["response_status", "error_code"])
        ModelCall.objects.create(
            session=session,
            student_message=student_message,
            provider=type(patient_gateway).__name__,
            model="unavailable",
            request_hash=request_hash(question=content, facts=facts),
            matched_fact_codes=[fact.code for fact in facts],
            status=ModelCallStatus.FAILED,
            error_code="gateway_error",
        )
        raise ModelUnavailableError("患者模型暂时不可用，请稍后重试。") from error

    allowed_codes = {fact.code for fact in facts}
    invalid = (
        not result.fact_codes
        or not set(result.fact_codes).issubset(allowed_codes)
        or _diagnosis_leaked(session, result.answer)
    )
    if invalid:
        result = GatewayResult(
            answer=" ".join(fact.patient_expression for fact in facts),
            fact_codes=[fact.code for fact in facts],
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
        call_status = ModelCallStatus.FAILED
        call_error = "response_validation_failed"
    else:
        call_status = ModelCallStatus.SUCCEEDED
        call_error = ""

    patient_message = _save_patient_response(
        student_message=student_message,
        result=result,
        hashed_request=request_hash(question=content, facts=facts),
        call_status=call_status,
        call_error=call_error,
    )
    return ExchangeResult(student_message, patient_message, reused)


SUBMISSION_FLOW = {
    SessionStage.INTERVIEW: (SubmissionType.HISTORY_SUMMARY, SessionStage.INITIAL_REASONING),
    SessionStage.INITIAL_REASONING: (
        SubmissionType.INITIAL_REASONING,
        SessionStage.TEST_SELECTION,
    ),
    SessionStage.TEST_SELECTION: (SubmissionType.TEST_SELECTION, SessionStage.FINAL_REASONING),
    SessionStage.FINAL_REASONING: (SubmissionType.FINAL_REASONING, SessionStage.COMPLETED),
}


def submit_stage(
    *,
    session: SimulationSession,
    student,
    submission_type: str,
    payload: dict,
) -> StageSubmission:
    require_active_session(session=session, student=student)
    now = timezone.now()
    completed = False
    with transaction.atomic():
        locked = SimulationSession.objects.select_for_update().select_related("assignment").get(
            pk=session.pk
        )
        if _expire_if_needed(locked, now=now):
            raise SessionExpiredError("考试时间已经结束，当前内容已自动保存。")
        expected = SUBMISSION_FLOW.get(locked.stage)
        if expected is None or submission_type != expected[0]:
            raise StageLockedError("提交类型与当前阶段不一致，不能返回修改上一阶段。")
        if StageSubmission.objects.filter(
            session=locked,
            submission_type=submission_type,
        ).exists():
            raise DuplicateSubmissionError("该阶段已经提交，不能覆盖历史内容。")
        if (
            locked.stage == SessionStage.INTERVIEW
            and Message.objects.filter(
                session=locked,
                role=MessageRole.STUDENT,
                response_status=ResponseStatus.PROCESSING,
            ).exists()
        ):
            raise StageLockedError("仍有患者回答正在生成，请等待回答完成后再结束问诊。")

        submission = StageSubmission.objects.create(
            session=locked,
            submission_type=submission_type,
            payload=payload,
        )
        previous = locked.stage
        locked.stage = expected[1]
        if locked.stage == SessionStage.COMPLETED:
            completed = True
            locked.status = SessionStatus.COMPLETED
            locked.completed_at = now
            locked.retention_expires_at = now + timedelta(days=RETENTION_DAYS)
            locked.save(
                update_fields=[
                    "stage",
                    "status",
                    "completed_at",
                    "retention_expires_at",
                    "updated_at",
                ]
            )
        else:
            locked.save(update_fields=["stage", "updated_at"])
        SessionStageEvent.objects.create(
            session=locked,
            from_stage=previous,
            to_stage=locked.stage,
        )
    if completed:
        generate_assessment(locked)
    return submission


def feedback_for_session(*, session: SimulationSession, student) -> dict:
    if session.student_id != student.id:
        raise AssignmentUnavailableError("无权访问该问诊反馈。")
    if session.assignment.feedback_released_at is None:
        raise FeedbackUnavailableError("教师尚未统一发布反馈。")
    assessment = generate_assessment(session)
    visible_results = list(session.score_results.filter(is_student_visible=True))
    review = latest_review(session)
    overrides = review_overrides(review)
    effective_by_code = {
        result.code: effective_score(result, review) for result in visible_results
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
                "effective_decision": effective_decision(result, review),
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
        "ai_feedback": assessment.ai_feedback or None,
        "teacher_comment": review.comment if review else "",
    }
