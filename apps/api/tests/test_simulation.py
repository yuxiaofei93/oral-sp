from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.cases.models import DiagnosisType, VersionStatus
from modules.cases.services import create_case_with_draft, publish_draft, update_draft
from modules.simulation.ai_evaluation import (
    AIEvaluationError,
    AIEvaluationGateway,
    AIGatewayResponse,
    run_ai_evaluation,
)
from modules.simulation.gateways import (
    GatewayResult,
    PatientGateway,
    RoutingResult,
)
from modules.simulation.models import (
    AIEvaluationRun,
    AIEvaluationStatus,
    AIScoreResult,
    AssignmentStudent,
    Message,
    MessageRole,
    ModelCallStatus,
    ResponseStatus,
    ScoreDecision,
    SessionAssessment,
    SessionStage,
    SessionStatus,
    SubmissionType,
    TeacherReview,
)
from modules.simulation.reviews import create_teacher_review
from modules.simulation.services import (
    AttemptAlreadyUsedError,
    StageLockedError,
    ask_patient,
    close_assignment,
    create_assignment,
    start_session,
    submit_stage,
)
from modules.teaching.models import ClassGroup, ClassMembership

User = get_user_model()
PASSWORD = "MolarTraining!2026"


class StaticAIEvaluationGateway(AIEvaluationGateway):
    provider = "deepseek"
    model = "deepseek-v4-flash"

    def __init__(self, *, invalid_evidence: bool = False):
        self.invalid_evidence = invalid_evidence
        self.payloads = []

    def evaluate(self, *, payload: dict) -> AIGatewayResponse:
        self.payloads.append(payload)
        evidence_ref = (
            "message:does-not-exist"
            if self.invalid_evidence
            else payload["conversation"][0]["ref"]
        )
        return AIGatewayResponse(
            data={
                "summary": "问诊表达清楚，可进一步使用开放式提问。",
                "items": [
                    {
                        "code": "score.communication",
                        "score": 0.75,
                        "confidence": 0.82,
                        "evidence_refs": [evidence_ref],
                        "reason": "提问简洁，并围绕病程获取了有效信息。",
                        "feedback": "可以先开放询问，再针对病程追问。",
                    }
                ],
            },
            provider=self.provider,
            model="DeepSeek-V4-Flash-0731",
            latency_ms=321,
            input_tokens=120,
            output_tokens=80,
        )


def make_user(identifier: str, role_code: str):
    user = User.objects.create_user(
        email=f"{identifier}@example.com",
        password=PASSWORD,
        display_name=role_code,
    )
    user.roles.add(Role.objects.get(code=role_code))
    return user


def make_exam_data(*, suffix="1"):
    teacher = make_user(f"1390000000{suffix}", RoleCode.TEACHER)
    student = make_user(f"1380000000{suffix}", RoleCode.STUDENT)
    case = create_case_with_draft(
        title_internal="牙龈疼痛标准病例",
        user=teacher,
    )
    draft = case.versions.get(status=VersionStatus.DRAFT)
    update_draft(
        draft=draft,
        data={
            "disease_tags": ["慢性牙周炎"],
            "patient_profile": {
                "display_name": "陈女士",
                "opening_statement": "医生您好，我的牙龈总是疼。",
            },
            "facts": [
                {
                    "code": "history.duration",
                    "category": "present_illness",
                    "standard_fact": "病程约三年",
                    "patient_expression": "差不多有三年了。",
                    "semantic_tags": ["多久", "病程"],
                    "synonyms": ["多长时间"],
                    "is_required": True,
                    "score": "2.00",
                }
            ],
            "diagnosis_rules": [
                {
                    "diagnosis_type": DiagnosisType.FINAL,
                    "name": "慢性牙周炎",
                    "aliases": ["牙周炎"],
                    "supporting_evidence": ["病程长"],
                }
            ],
            "tests": [
                {
                    "code": "periodontal.probe",
                    "name": "牙周探诊",
                    "result_text": "探诊深度增加",
                    "teacher_interpretation": "支持牙周组织破坏",
                }
            ],
            "scoring_items": [
                {
                    "code": "score.summary",
                    "dimension": "summary",
                    "label": "病史摘要关键要素",
                    "max_score": "1.00",
                    "evaluation_method": "rule",
                    "matching_config": {
                        "source": "submission_keywords",
                        "submission_type": "history_summary",
                        "keywords": ["牙龈疼痛", "三年"],
                        "match": "all",
                    },
                },
                {
                    "code": "score.tests",
                    "dimension": "test_plan",
                    "label": "检查选择",
                    "max_score": "2.00",
                    "evaluation_method": "rule",
                    "matching_config": {
                        "source": "tests",
                        "test_codes": ["periodontal.probe"],
                    },
                },
                {
                    "code": "score.final",
                    "dimension": "final_reasoning",
                    "label": "最终诊断",
                    "max_score": "3.00",
                    "evaluation_method": "rule",
                    "matching_config": {
                        "source": "diagnoses",
                        "diagnosis_names": ["慢性牙周炎"],
                    },
                },
                {
                    "code": "score.communication",
                    "dimension": "communication",
                    "label": "沟通质量",
                    "max_score": "1.00",
                    "evaluation_method": "ai",
                    "matching_config": {},
                    "is_student_visible": False,
                },
            ],
        },
    )
    published = publish_draft(draft=draft, user=teacher).version
    class_group = ClassGroup.objects.create(
        code=f"CLASS-{suffix}",
        name="第一教学班",
        created_by=teacher,
    )
    ClassMembership.objects.create(class_group=class_group, student=student)
    now = timezone.now()
    assignment = create_assignment(
        title="牙周问诊练习",
        case_version=published,
        class_group=class_group,
        duration_minutes=20,
        opens_at=now - timedelta(minutes=5),
        deadline_at=now + timedelta(hours=1),
        user=teacher,
    )
    return teacher, student, assignment


@pytest.mark.django_db
def test_teacher_assignment_snapshots_roster_and_student_response_hides_answers():
    teacher, student, assignment = make_exam_data(suffix="1")
    assert AssignmentStudent.objects.filter(assignment=assignment, student=student).exists()

    client = APIClient()
    client.force_authenticate(student)
    response = client.get(reverse("student-assignment-list"))

    assert response.status_code == 200
    assert "case_title" not in response.json()[0]
    assert response.json()[0]["attempt_status"] == "not_started"
    serialized = str(response.json())
    assert "慢性牙周炎" not in serialized
    assert "探诊深度增加" not in serialized

    client.force_authenticate(teacher)
    teacher_response = client.get(reverse("teacher-assignment-list"))
    assert teacher_response.status_code == 200
    assert teacher_response.json()[0]["student_count"] == 1
    assert teacher_response.json()[0]["not_started_count"] == 1
    assert teacher_response.json()[0]["active_count"] == 0

    assignment.class_group.memberships.filter(student=student).delete()
    assert AssignmentStudent.objects.filter(assignment=assignment, student=student).exists()


@pytest.mark.django_db
def test_session_start_resumes_active_but_never_grants_second_attempt():
    _, student, assignment = make_exam_data(suffix="2")
    first = start_session(assignment=assignment, student=student)
    second = start_session(assignment=assignment, student=student)

    assert first.created is True
    assert second.created is False
    assert second.session.id == first.session.id

    flow = [
        SubmissionType.HISTORY_SUMMARY,
        SubmissionType.INITIAL_REASONING,
        SubmissionType.TEST_SELECTION,
        SubmissionType.FINAL_REASONING,
    ]
    for submission_type in flow:
        submit_stage(
            session=first.session,
            student=student,
            submission_type=submission_type,
            payload={"text": submission_type},
        )

    first.session.refresh_from_db()
    assert first.session.status == SessionStatus.COMPLETED
    with pytest.raises(AttemptAlreadyUsedError):
        start_session(assignment=assignment, student=student)


@pytest.mark.django_db
def test_question_is_idempotent_and_sent_messages_are_immutable():
    _, student, assignment = make_exam_data(suffix="3")
    session = start_session(assignment=assignment, student=student).session

    first = ask_patient(
        session=session,
        student=student,
        content="这个情况有多久了？",
        client_message_id="question_0001",
    )
    second = ask_patient(
        session=session,
        student=student,
        content="这个情况有多久了？",
        client_message_id="question_0001",
    )

    assert first.patient_message.content == "差不多有三年了。"
    assert second.reused is True
    assert second.patient_message.id == first.patient_message.id
    assert Message.objects.filter(session=session).count() == 2

    first.student_message.content = "试图覆盖问题"
    with pytest.raises(ValidationError):
        first.student_message.save()
    with pytest.raises(ValidationError):
        first.student_message.delete()


@pytest.mark.django_db
def test_question_matches_legacy_tags_joined_with_chinese_delimiters():
    _, student, assignment = make_exam_data(suffix="0")
    assignment.case_version.facts.filter(code="history.duration").update(
        semantic_tags=["多久、病程"],
        synonyms=["多长时间；几年"],
    )
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="请问这个情况有多久了？",
        client_message_id="question_delimiter_01",
    )

    assert exchange.patient_message.content == "差不多有三年了。"


class DiagnosisLeakingGateway(PatientGateway):
    def answer(self, *, question, facts, history):
        del question, history
        return GatewayResult(
            answer="医生，我这就是慢性牙周炎。",
            fact_codes=[facts[0].code],
            provider="test-provider",
            model="leaky-model",
            latency_ms=12,
        )


@pytest.mark.django_db
def test_diagnosis_leak_is_replaced_by_safe_fact_response_and_audited():
    _, student, assignment = make_exam_data(suffix="4")
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="你的病程有多久？",
        client_message_id="question_0002",
        gateway=DiagnosisLeakingGateway(),
    )

    assert exchange.patient_message.content == "差不多有三年了。"
    call = session.model_calls.get(patient_message__isnull=False)
    assert call.status == ModelCallStatus.FAILED
    assert call.error_code == "response_validation_failed"


class SemanticRoutingGateway(PatientGateway):
    def __init__(self):
        self.histories = []

    def route(self, *, question, facts, history):
        assert question == "不舒服从什么时候开始的？"
        self.histories.append(history)
        return RoutingResult(
            fact_codes=["history.duration"],
            confidence=0.96,
            provider="deepseek",
            model="deepseek-v4-flash",
            latency_ms=20,
            input_tokens=40,
            output_tokens=8,
        )

    def answer(self, *, question, facts, history):
        del question
        assert history == self.histories[-1]
        return GatewayResult(
            answer=facts[0].patient_expression,
            fact_codes=[facts[0].code],
            provider="deepseek",
            model="deepseek-v4-flash",
            latency_ms=25,
            input_tokens=30,
            output_tokens=10,
        )


@pytest.mark.django_db
def test_semantic_router_maps_natural_question_without_teacher_keyword():
    _, student, assignment = make_exam_data(suffix="0")
    assignment.case_version.facts.filter(code="history.duration").update(
        semantic_tags=[],
        synonyms=[],
    )
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="不舒服从什么时候开始的？",
        client_message_id="semantic_route_question_01",
        gateway=SemanticRoutingGateway(),
    )

    assert exchange.patient_message.content == "差不多有三年了。"
    route_call = session.model_calls.get(prompt_version="patient-route-v1")
    assert route_call.provider == "deepseek"
    assert route_call.matched_fact_codes == ["history.duration"]
    answer_call = session.model_calls.get(patient_message__isnull=False)
    assert answer_call.matched_fact_codes == ["history.duration"]


@pytest.mark.django_db
def test_unrelated_question_uses_unknown_response_after_empty_route():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="你今天坐什么交通工具来的？",
        client_message_id="unrelated_question_01",
    )

    assert exchange.patient_message.content == "这个我不太清楚。"
    assert session.model_calls.filter(prompt_version="patient-route-v1").count() == 1
    answer_call = session.model_calls.get(patient_message__isnull=False)
    assert answer_call.provider == "rules"
    assert answer_call.matched_fact_codes == []


@pytest.mark.django_db
def test_stage_submission_is_ordered_and_locks_further_patient_questions():
    _, student, assignment = make_exam_data(suffix="5")
    session = start_session(assignment=assignment, student=student).session

    submission = submit_stage(
        session=session,
        student=student,
        submission_type=SubmissionType.HISTORY_SUMMARY,
        payload={"summary": "牙龈疼痛三年"},
    )
    session.refresh_from_db()
    assert session.stage == SessionStage.INITIAL_REASONING

    with pytest.raises(StageLockedError):
        ask_patient(
            session=session,
            student=student,
            content="还有别的不舒服吗？",
            client_message_id="question_0003",
        )
    submission.payload = {"summary": "覆盖"}
    with pytest.raises(ValidationError):
        submission.save()


@pytest.mark.django_db
def test_server_expires_session_and_feedback_is_released_only_after_close():
    teacher, student, assignment = make_exam_data(suffix="6")
    session = start_session(assignment=assignment, student=student).session
    past_start = timezone.now() - timedelta(minutes=2)
    past_deadline = timezone.now() - timedelta(minutes=1)
    type(session).objects.filter(pk=session.pk).update(
        started_at=past_start,
        deadline_at=past_deadline,
    )

    client = APIClient()
    client.force_authenticate(student)
    detail = client.get(reverse("student-session-detail", kwargs={"session_id": session.id}))
    assert detail.status_code == 200
    assert detail.json()["status"] == SessionStatus.EXPIRED
    assert detail.json()["remaining_seconds"] == 0

    feedback_url = reverse("student-session-feedback", kwargs={"session_id": session.id})
    assert client.get(feedback_url).status_code == 403

    client.force_authenticate(teacher)
    close_url = reverse("teacher-assignment-close", kwargs={"assignment_id": assignment.id})
    release_url = reverse(
        "teacher-assignment-release-feedback",
        kwargs={"assignment_id": assignment.id},
    )
    assert client.post(close_url).status_code == 200
    assert client.post(release_url).status_code == 200

    client.force_authenticate(student)
    feedback = client.get(feedback_url)
    assert feedback.status_code == 200
    assert feedback.json()["standard_diagnoses"][0]["name"] == "慢性牙周炎"
    assert feedback.json()["standard_tests"][0]["name"] == "牙周探诊"


@pytest.mark.django_db
def test_student_cannot_access_another_students_session():
    _, student, assignment = make_exam_data(suffix="7")
    outsider = make_user("13899999997", RoleCode.STUDENT)
    session = start_session(assignment=assignment, student=student).session
    client = APIClient()
    client.force_authenticate(outsider)

    response = client.get(reverse("student-session-detail", kwargs={"session_id": session.id}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_unpublished_case_cannot_be_assigned_through_api():
    teacher, _, assignment = make_exam_data(suffix="8")
    draft = assignment.case_version.case.versions.get(status=VersionStatus.DRAFT)
    client = APIClient()
    client.force_authenticate(teacher)
    response = client.post(
        reverse("teacher-assignment-list"),
        {
            "title": "错误任务",
            "case_version_id": str(draft.id),
            "class_group_id": str(assignment.class_group_id),
            "duration_minutes": 20,
            "opens_at": timezone.now().isoformat(),
            "deadline_at": (timezone.now() + timedelta(hours=1)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_student_api_runs_idempotent_interview_exchange():
    _, student, assignment = make_exam_data(suffix="9")
    client = APIClient()
    client.force_authenticate(student)

    started = client.post(
        reverse("student-session-start", kwargs={"assignment_id": assignment.id})
    )
    assert started.status_code == 201
    session_id = started.json()["session"]["id"]
    assert started.json()["session"]["opening_statement"] == "医生您好，我的牙龈总是疼。"

    message_url = reverse("student-session-message", kwargs={"session_id": session_id})
    payload = {"content": "病程有多久？", "client_message_id": "api_question_0001"}
    first = client.post(message_url, payload, format="json")
    second = client.post(message_url, payload, format="json")

    assert first.status_code == 200
    assert first.json()["patient_message"]["content"] == "差不多有三年了。"
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["patient_message"]["id"] == first.json()["patient_message"]["id"]


@pytest.mark.django_db
def test_assignment_options_only_include_teachers_published_cases_and_classes():
    teacher, _, assignment = make_exam_data(suffix="0")
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.get(reverse("teacher-assignment-options"))

    assert response.status_code == 200
    assert response.json()["case_versions"] == [
        {
            "id": str(assignment.case_version_id),
            "case_code": assignment.case_version.case.code,
            "title": "牙龈疼痛标准病例",
            "version_number": 1,
            "suggested_duration_minutes": 20,
        }
    ]
    assert response.json()["class_groups"][0]["id"] == str(assignment.class_group_id)
    assert response.json()["class_groups"][0]["student_count"] == 1


def complete_scored_session(*, session, student, correct: bool):
    if correct:
        ask_patient(
            session=session,
            student=student,
            content="牙龈疼痛有多久了？",
            client_message_id="scoring_question_01",
        )
    answers = {
        SubmissionType.HISTORY_SUMMARY: "牙龈疼痛已有三年",
        SubmissionType.INITIAL_REASONING: "考虑牙周组织疾病",
        SubmissionType.TEST_SELECTION: "申请牙周探诊",
        SubmissionType.FINAL_REASONING: "最终诊断为慢性牙周炎",
    }
    for submission_type in (
        SubmissionType.HISTORY_SUMMARY,
        SubmissionType.INITIAL_REASONING,
        SubmissionType.TEST_SELECTION,
        SubmissionType.FINAL_REASONING,
    ):
        submit_stage(
            session=session,
            student=student,
            submission_type=submission_type,
            payload={"text": answers[submission_type] if correct else "未明确判断"},
        )


@pytest.mark.django_db
def test_rule_scoring_is_traceable_and_marks_non_rule_items_pending():
    _, student, assignment = make_exam_data(suffix="1")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=True)

    assessment = SessionAssessment.objects.get(session=session)
    assert assessment.automatic_score == 8
    assert assessment.scored_maximum == 8
    assert assessment.maximum_score == 9
    assert assessment.provisional is True
    assert assessment.omissions == []
    assert assessment.errors == []

    fact_result = session.score_results.get(code="fact:history.duration")
    assert fact_result.decision == ScoreDecision.ACHIEVED
    assert len(fact_result.evidence_message_ids) == 2
    assert "牙龈疼痛有多久了" in fact_result.evidence_excerpt
    assert session.score_results.get(code="score.communication").decision == ScoreDecision.PENDING

    assessment.feedback_summary = "试图覆盖"
    with pytest.raises(ValidationError):
        assessment.save()


@pytest.mark.django_db
def test_deepseek_ai_evaluation_is_traceable_idempotent_and_teacher_overridable(monkeypatch):
    teacher, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=True)
    gateway = StaticAIEvaluationGateway()
    monkeypatch.setattr(
        "modules.simulation.ai_evaluation.get_ai_evaluation_gateway",
        lambda: gateway,
    )
    client = APIClient()
    client.force_authenticate(teacher)
    evaluation_url = reverse(
        "teacher-session-ai-evaluation",
        kwargs={"session_id": session.id},
    )

    created = client.post(evaluation_url, {}, format="json")
    assert created.status_code == 201
    assert created.json()["requested_by_id"] == str(teacher.id)
    assert created.json()["requested_by_name"] == teacher.display_name
    assert created.json()["provider"] == "deepseek"
    assert created.json()["model"] == "deepseek-v4-flash"
    assert created.json()["resolved_model"] == "DeepSeek-V4-Flash-0731"
    assert created.json()["results"][0]["score"] == 0.75
    assert created.json()["results"][0]["confidence"] == 0.82
    assert "牙龈疼痛有多久了" in created.json()["results"][0]["evidence_excerpt"]
    assert "student" not in gateway.payloads[0]
    assert student.email not in str(gateway.payloads[0])

    reused = client.post(evaluation_url, {}, format="json")
    assert reused.status_code == 200
    assert AIEvaluationRun.objects.filter(session=session).count() == 1
    assert len(gateway.payloads) == 1

    regenerated = client.post(evaluation_url, {"force": True}, format="json")
    assert regenerated.status_code == 201
    assert AIEvaluationRun.objects.filter(session=session).count() == 2
    assert AIScoreResult.objects.filter(run__session=session).count() == 2

    record_url = reverse("teacher-session-record", kwargs={"session_id": session.id})
    record = client.get(record_url)
    assert record.status_code == 200
    assert record.json()["assessment"]["final_score"] == 8.75
    assert record.json()["assessment"]["scored_maximum"] == 9.0
    assert record.json()["assessment"]["provisional"] is False
    communication = next(
        item
        for item in record.json()["assessment"]["scoring_items"]
        if item["code"] == "score.communication"
    )
    assert communication["ai_score"] == 0.75
    assert communication["effective_score"] == 0.75

    reviewed = client.post(
        reverse("teacher-session-review", kwargs={"session_id": session.id}),
        {
            "comment": "已人工核对沟通表现。",
            "scores": [
                {
                    "code": "score.communication",
                    "score": "0.50",
                    "reason": "开放式提问仍可加强。",
                }
            ],
        },
        format="json",
    )
    assert reviewed.status_code == 201
    assert reviewed.json()["final_score"] == 8.5

    client.post(reverse("teacher-assignment-close", kwargs={"assignment_id": assignment.id}))
    released = client.post(
        reverse(
            "teacher-assignment-release-feedback",
            kwargs={"assignment_id": assignment.id},
        )
    )
    assert released.status_code == 200
    frozen = client.post(evaluation_url, {"force": True}, format="json")
    assert frozen.status_code == 409
    assert frozen.json()["code"] == "feedback_frozen"

    client.force_authenticate(student)
    feedback = client.get(
        reverse("student-session-feedback", kwargs={"session_id": session.id})
    )
    assert feedback.status_code == 200
    assert "score.communication" not in {
        item["code"] for item in feedback.json()["scoring_items"]
    }
    assert feedback.json()["ai_feedback"] is None


@pytest.mark.django_db
def test_ai_evaluation_rejects_invented_evidence_without_partial_scores():
    teacher, student, assignment = make_exam_data(suffix="4")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=True)
    session.refresh_from_db()

    with pytest.raises(AIEvaluationError) as captured:
        run_ai_evaluation(
            session=session,
            requested_by=teacher,
            gateway=StaticAIEvaluationGateway(invalid_evidence=True),
        )

    assert captured.value.code == "invalid_ai_evidence"
    failed = AIEvaluationRun.objects.get(session=session)
    assert failed.status == AIEvaluationStatus.FAILED
    assert failed.error_code == "invalid_ai_evidence"
    assert not AIScoreResult.objects.filter(run=failed).exists()


@pytest.mark.django_db
def test_missing_answers_generate_omissions_errors_and_teacher_record():
    teacher, student, assignment = make_exam_data(suffix="2")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=False)
    assessment = SessionAssessment.objects.get(session=session)

    assert assessment.automatic_score == 0
    assert assessment.scored_maximum == 8
    assert len(assessment.omissions) == 4
    assert len(assessment.errors) == 2

    client = APIClient()
    client.force_authenticate(teacher)
    rows = client.get(
        reverse("teacher-assignment-responses", kwargs={"assignment_id": assignment.id})
    )
    assert rows.status_code == 200
    assert rows.json()[0]["display_name"] == RoleCode.STUDENT
    assert rows.json()[0]["score"]["automatic_score"] == 0

    record = client.get(reverse("teacher-session-record", kwargs={"session_id": session.id}))
    assert record.status_code == 200
    assert record.json()["student_email"] == student.email
    assert len(record.json()["messages"]) == 0
    assert len(record.json()["submissions"]) == 4
    assert len(record.json()["assessment"]["scoring_items"]) == 5
    assert record.json()["standard_diagnoses"][0]["name"] == "慢性牙周炎"

    outsider = make_user("13999999992", RoleCode.TEACHER)
    client.force_authenticate(outsider)
    assert (
        client.get(reverse("teacher-session-record", kwargs={"session_id": session.id})).status_code
        == 404
    )

    client.force_authenticate(student)
    assert (
        client.get(reverse("teacher-session-record", kwargs={"session_id": session.id})).status_code
        == 403
    )


@pytest.mark.django_db
def test_student_feedback_contains_only_visible_scoring_details_after_release():
    teacher, student, assignment = make_exam_data(suffix="3")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=True)
    client = APIClient()
    client.force_authenticate(teacher)
    client.post(reverse("teacher-assignment-close", kwargs={"assignment_id": assignment.id}))
    client.post(
        reverse(
            "teacher-assignment-release-feedback",
            kwargs={"assignment_id": assignment.id},
        )
    )

    client.force_authenticate(student)
    feedback = client.get(
        reverse("student-session-feedback", kwargs={"session_id": session.id})
    )
    assert feedback.status_code == 200
    assert feedback.json()["score"] == {
        "automatic_score": 8.0,
        "final_score": 8.0,
        "scored_maximum": 8.0,
        "maximum_score": 8.0,
        "provisional": False,
    }
    codes = [item["code"] for item in feedback.json()["scoring_items"]]
    assert "score.communication" not in codes
    assert "score.final" in codes
    assert feedback.json()["ai_feedback"] is None


@pytest.mark.django_db
def test_teacher_review_is_versioned_visible_after_release_and_then_frozen():
    teacher, student, assignment = make_exam_data(suffix="5")
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=True)
    client = APIClient()
    client.force_authenticate(teacher)
    review_url = reverse("teacher-session-review", kwargs={"session_id": session.id})
    payload = {
        "comment": "诊断方向正确，但表述依据还可更完整。",
        "scores": [
            {
                "code": "score.final",
                "score": "2.00",
                "reason": "最终诊断正确，支持依据不够完整。",
            }
        ],
    }

    created = client.post(review_url, payload, format="json")
    assert created.status_code == 201
    assert created.json()["revision"] == 1
    assert created.json()["final_score"] == 7.0
    assert created.json()["provisional"] is True
    assert client.post(review_url, payload, format="json").status_code == 200
    assert TeacherReview.objects.filter(session=session).count() == 1
    revised_comment = "诊断方向正确，请继续补充关键支持依据。"
    revised = client.post(
        review_url,
        {"comment": revised_comment, "scores": []},
        format="json",
    )
    assert revised.status_code == 201
    assert revised.json()["revision"] == 2
    assert revised.json()["final_score"] == 7.0
    assert revised.json()["score_overrides"]["score.final"]["score"] == "2.00"
    first_review = TeacherReview.objects.get(session=session, revision=1)
    first_review.comment = "试图覆盖历史"
    with pytest.raises(ValidationError):
        first_review.save()

    record = client.get(reverse("teacher-session-record", kwargs={"session_id": session.id}))
    assert record.status_code == 200
    assert record.json()["assessment"]["final_score"] == 7.0
    final_item = next(
        item
        for item in record.json()["assessment"]["scoring_items"]
        if item["code"] == "score.final"
    )
    assert final_item["automatic_score"] == 3.0
    assert final_item["teacher_score"] == 2.0
    assert final_item["effective_score"] == 2.0
    assert record.json()["latest_review"]["revision"] == 2
    assert record.json()["latest_review"]["reviewer_id"] == str(teacher.id)
    rows = client.get(
        reverse("teacher-assignment-responses", kwargs={"assignment_id": assignment.id})
    )
    assert rows.json()[0]["score"]["final_score"] == 7.0

    client.post(reverse("teacher-assignment-close", kwargs={"assignment_id": assignment.id}))
    client.post(
        reverse(
            "teacher-assignment-release-feedback",
            kwargs={"assignment_id": assignment.id},
        )
    )
    client.force_authenticate(student)
    feedback = client.get(
        reverse("student-session-feedback", kwargs={"session_id": session.id})
    )
    assert feedback.status_code == 200
    assert feedback.json()["score"]["automatic_score"] == 8.0
    assert feedback.json()["score"]["final_score"] == 7.0
    assert feedback.json()["teacher_comment"] == revised_comment
    final_feedback = next(
        item for item in feedback.json()["scoring_items"] if item["code"] == "score.final"
    )
    assert final_feedback["effective_score"] == 2.0
    assert final_feedback["effective_decision"] == ScoreDecision.PARTIAL
    assert final_feedback["adjustment_reason"] == payload["scores"][0]["reason"]

    client.force_authenticate(teacher)
    frozen = client.post(
        review_url,
        {"comment": "尝试发布后修改", "scores": []},
        format="json",
    )
    assert frozen.status_code == 409
    assert frozen.json()["code"] == "teacher_review_frozen"


@pytest.mark.django_db
def test_teacher_review_rejects_active_session_invalid_scores_and_unauthorized_users():
    teacher, student, assignment = make_exam_data(suffix="6")
    session = start_session(assignment=assignment, student=student).session
    review_url = reverse("teacher-session-review", kwargs={"session_id": session.id})
    client = APIClient()
    client.force_authenticate(teacher)
    active = client.post(review_url, {"comment": "过早复核", "scores": []}, format="json")
    assert active.status_code == 409

    complete_scored_session(session=session, student=student, correct=True)
    missing_reason = client.post(
        review_url,
        {"comment": "", "scores": [{"code": "score.final", "score": "2.00", "reason": ""}]},
        format="json",
    )
    assert missing_reason.status_code == 400
    invalid_score = client.post(
        review_url,
        {
            "comment": "",
            "scores": [
                {"code": "score.final", "score": "4.00", "reason": "超过满分"}
            ],
        },
        format="json",
    )
    assert invalid_score.status_code == 409

    outsider = make_user("13999999996", RoleCode.TEACHER)
    client.force_authenticate(outsider)
    assert (
        client.post(review_url, {"comment": "越权", "scores": []}, format="json").status_code
        == 404
    )
    client.force_authenticate(student)
    assert (
        client.post(review_url, {"comment": "越权", "scores": []}, format="json").status_code
        == 403
    )


@pytest.mark.django_db
def test_assignment_statistics_and_csv_export_use_latest_review_safely():
    teacher, student, assignment = make_exam_data(suffix="7")
    student.display_name = "=SUM(1,1)"
    student.save(update_fields=["display_name"])
    session = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=session, student=student, correct=False)
    client = APIClient()
    client.force_authenticate(teacher)
    client.post(
        reverse("teacher-session-review", kwargs={"session_id": session.id}),
        {
            "comment": "+需要重点复习诊断依据",
            "scores": [
                {
                    "code": "score.final",
                    "score": "2.00",
                    "reason": "诊断方向接近，但依据不完整。",
                }
            ],
        },
        format="json",
    )

    statistics_url = reverse(
        "teacher-assignment-statistics",
        kwargs={"assignment_id": assignment.id},
    )
    export_url = reverse(
        "teacher-assignment-export-csv",
        kwargs={"assignment_id": assignment.id},
    )
    statistics = client.get(statistics_url)
    assert statistics.status_code == 200
    assert statistics.json()["summary"]["completion_rate"] == 100.0
    assert statistics.json()["summary"]["average_score"] == 2.0
    assert statistics.json()["summary"]["average_score_percentage"] == 22.22
    assert statistics.json()["summary"]["assessed_count"] == 1
    assert statistics.json()["frequent_omissions"][0]["count"] == 1
    assert statistics.json()["common_errors"][0]["count"] == 1

    exported = client.get(export_url)
    assert exported.status_code == 200
    assert exported["Content-Type"].startswith("text/csv")
    assert exported.content.startswith("\ufeff".encode())
    csv_text = exported.content.decode("utf-8-sig")
    assert "学生姓名,邮箱,作答状态" in csv_text
    assert "'=SUM(1,1)" in csv_text
    assert student.email in csv_text
    assert "'+需要重点复习诊断依据" in csv_text
    assert ",0.0,2.0,8.0,9.0,是," in csv_text

    outsider = make_user("13999999997", RoleCode.TEACHER)
    client.force_authenticate(outsider)
    assert client.get(statistics_url).status_code == 404
    assert client.get(export_url).status_code == 404
    client.force_authenticate(student)
    assert client.get(statistics_url).status_code == 403
    assert client.get(export_url).status_code == 403


@pytest.mark.django_db
def test_forced_collection_starts_retention_period_at_session_end():
    _, student, assignment = make_exam_data(suffix="8")
    session = start_session(assignment=assignment, student=student).session

    close_assignment(assignment=assignment)

    session.refresh_from_db()
    assert session.status == SessionStatus.EXPIRED
    assert session.completed_at is not None
    assert session.retention_expires_at == session.completed_at + timedelta(days=180)


@pytest.mark.django_db
def test_retention_command_previews_then_deletes_only_safe_expired_data():
    teacher, student, assignment = make_exam_data(suffix="8")
    completed = start_session(assignment=assignment, student=student).session
    complete_scored_session(session=completed, student=student, correct=True)
    completed.refresh_from_db()
    create_teacher_review(
        session=completed,
        reviewer=teacher,
        comment="清理测试评语",
        scores=[],
    )
    ai_run = run_ai_evaluation(
        session=completed,
        requested_by=teacher,
        gateway=StaticAIEvaluationGateway(),
    ).run
    now = timezone.now()
    type(assignment).objects.filter(pk=assignment.pk).update(deadline_at=now - timedelta(seconds=1))
    type(completed).objects.filter(pk=completed.pk).update(
        retention_expires_at=now - timedelta(seconds=1)
    )

    _, stale_student, stale_assignment = make_exam_data(suffix="9")
    stale = start_session(assignment=stale_assignment, student=stale_student).session
    type(stale).objects.filter(pk=stale.pk).update(
        started_at=now - timedelta(minutes=2),
        deadline_at=now - timedelta(minutes=1),
        retention_expires_at=now - timedelta(seconds=1),
    )

    preview_output = StringIO()
    call_command("purge_expired_simulation_data", stdout=preview_output)
    assert "待落库的超时会话：1" in preview_output.getvalue()
    assert "可清理会话：1" in preview_output.getvalue()
    assert "预览模式：未修改任何数据" in preview_output.getvalue()
    assert type(completed).objects.filter(pk=completed.pk).exists()
    stale.refresh_from_db()
    assert stale.status == SessionStatus.ACTIVE

    execute_output = StringIO()
    call_command("purge_expired_simulation_data", execute=True, stdout=execute_output)
    assert "已落库超时会话 1 个" in execute_output.getvalue()
    assert "已删除会话 1 个" in execute_output.getvalue()
    assert not type(completed).objects.filter(pk=completed.pk).exists()
    assert not TeacherReview.objects.filter(session_id=completed.id).exists()
    assert not AIEvaluationRun.objects.filter(pk=ai_run.pk).exists()
    assert not AIScoreResult.objects.filter(run_id=ai_run.pk).exists()
    stale.refresh_from_db()
    assert stale.status == SessionStatus.EXPIRED
    assert stale.retention_expires_at == stale.completed_at + timedelta(days=180)


@pytest.mark.django_db
def test_interview_cannot_finish_while_patient_answer_is_processing():
    _, student, assignment = make_exam_data(suffix="4")
    session = start_session(assignment=assignment, student=student).session
    Message.objects.create(
        session=session,
        sequence=1,
        role=MessageRole.STUDENT,
        content="仍在等待回答的问题",
        client_message_id="processing_question_01",
        response_status=ResponseStatus.PROCESSING,
    )

    with pytest.raises(StageLockedError, match="正在生成"):
        submit_stage(
            session=session,
            student=student,
            submission_type=SubmissionType.HISTORY_SUMMARY,
            payload={"text": "尝试提前结束"},
        )
