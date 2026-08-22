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
from modules.cases.models import (
    DiagnosisType,
    PhysicalExam,
    PhysicalExamAsset,
    ScoringItem,
    StoredAsset,
    VersionStatus,
)
from modules.cases.services import create_case_with_draft, publish_draft, update_draft
from modules.simulation.gateways import (
    GatewayResult,
    PatientGateway,
    RoutingResult,
)
from modules.simulation.models import (
    AssignmentStudent,
    Message,
    MessageKind,
    MessageRole,
    ModelCallStatus,
    PhysicalExamRelease,
    ResponseStatus,
    ScoreDecision,
    SessionAssessment,
    SessionStage,
    SessionStatus,
    SubmissionType,
    TeacherReview,
)
from modules.simulation.reviews import create_teacher_review
from modules.simulation.scoring import generate_assessment
from modules.simulation.services import (
    AttemptAlreadyUsedError,
    CaseDraftConflictError,
    SessionLockedError,
    ask_patient,
    close_assignment,
    complete_session,
    create_assignment,
    save_case_draft,
    start_session,
)
from modules.teaching.models import ClassGroup, ClassMembership

User = get_user_model()
PASSWORD = "MolarTraining!2026"


def test_local_router_only_recognizes_an_explicit_oral_examination_request():
    gateway = PatientGateway()

    request = gateway.route(
        question="可以让我检查一下您的口腔吗？",
        facts=[],
        history=[],
        physical_exam_available=True,
    )
    symptom_question = gateway.route(
        question="您自己有看到口腔里面红肿吗？",
        facts=[],
        history=[],
        physical_exam_available=True,
    )

    assert request.intent == "physical_exam_request"
    assert request.confidence == 1.0
    assert symptom_question.intent == "patient_question"


def make_user(identifier: str, role_code: str):
    user = User.objects.create_user(
        email=f"{identifier}@example.com",
        password=PASSWORD,
        display_name=role_code,
    )
    user.roles.add(Role.objects.get(code=role_code))
    return user


def make_exam_data(*, suffix="1", patient_prompt=""):
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
            "patient_prompt_mode": "custom" if patient_prompt else "default",
            "patient_prompt": patient_prompt,
            "patient_profile": {
                "display_name": "陈女士",
                "opening_statement": "医生您好，我的牙龈总是疼。",
            },
            "physical_exam": {
                "findings_text": "全口牙龈红肿，探诊易出血。",
                "consent_text": "可以，麻烦您检查吧。",
            },
            "facts": [
                {
                    "code": "history.duration",
                    "standard_fact": "牙龈疼痛病程约三年",
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
                    "code": "score.history.duration",
                    "dimension": "history",
                    "label": "询问牙龈疼痛病程",
                    "max_score": "2.00",
                    "evaluation_method": "rule",
                    "matching_config": {
                        "source": "history_facts",
                        "fact_codes": ["history.duration"],
                    },
                },
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
                    "evaluation_method": "teacher",
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

    complete_session(
        session=first.session,
        student=student,
        case_record=case_record_payload(correct=True),
        expected_revision=0,
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
        content="牙龈疼痛有多久了？",
        client_message_id="question_0001",
    )
    second = ask_patient(
        session=session,
        student=student,
        content="牙龈疼痛有多久了？",
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
def test_local_router_matches_fact_content():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="牙龈疼痛有多久了？",
        client_message_id="question_fact_content_01",
    )

    assert exchange.patient_message.content == "差不多有三年了。"


class DiagnosisLeakingGateway(PatientGateway):
    def answer(self, *, question, facts, history, patient_prompt):
        del question, history, patient_prompt
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
        content="你的牙龈疼痛有多久？",
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
        self.patient_prompts = []

    def route(self, *, question, facts, history, physical_exam_available=False):
        assert question == "不舒服从什么时候开始的？"
        assert physical_exam_available is True
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

    def answer(self, *, question, facts, history, patient_prompt):
        del question
        assert history == self.histories[-1]
        self.patient_prompts.append(patient_prompt)
        return GatewayResult(
            answer="差不多有三年了。",
            fact_codes=[facts[0].code],
            provider="deepseek",
            model="deepseek-v4-flash",
            latency_ms=25,
            input_tokens=30,
            output_tokens=10,
        )


@pytest.mark.django_db
def test_semantic_router_maps_natural_question_without_teacher_keyword():
    _, student, assignment = make_exam_data(
        suffix="0",
        patient_prompt="请表现得有些紧张，只用一两句话回答。",
    )
    session = start_session(assignment=assignment, student=student).session
    Message.objects.bulk_create(
        [
            Message(
                session=session,
                sequence=index * 2 + offset,
                role=role,
                content=f"第 {index + 1} 轮{content}",
            )
            for index in range(7)
            for offset, role, content in (
                (1, MessageRole.STUDENT, "学生问题"),
                (2, MessageRole.PATIENT, "患者回答"),
            )
        ]
    )
    session.last_message_sequence = 14
    session.save(update_fields=["last_message_sequence", "updated_at"])

    gateway = SemanticRoutingGateway()
    exchange = ask_patient(
        session=session,
        student=student,
        content="不舒服从什么时候开始的？",
        client_message_id="semantic_route_question_01",
        gateway=gateway,
    )

    assert exchange.patient_message.content == "差不多有三年了。"
    assert gateway.patient_prompts == ["请表现得有些紧张，只用一两句话回答。"]
    assert len(gateway.histories[0]) == 14
    assert gateway.histories[0][0]["content"] == "第 1 轮学生问题"
    assert gateway.histories[0][-1]["content"] == "第 7 轮患者回答"
    route_call = session.model_calls.get(prompt_version="patient-route-v2")
    assert route_call.provider == "deepseek"
    assert route_call.matched_fact_codes == ["history.duration"]
    answer_call = session.model_calls.get(patient_message__isnull=False)
    assert answer_call.matched_fact_codes == ["history.duration"]


class WrittenFactRepeatingGateway(PatientGateway):
    def answer(self, *, question, facts, history, patient_prompt):
        del question, history, patient_prompt
        return GatewayResult(
            answer=facts[0].patient_expression,
            fact_codes=[facts[0].code],
            provider="test-provider",
            model="written-note-model",
            latency_ms=10,
        )


@pytest.mark.django_db
def test_written_fact_is_replaced_by_spoken_response_and_audited():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="牙龈疼痛有多久了？",
        client_message_id="written_fact_question_01",
        gateway=WrittenFactRepeatingGateway(),
    )

    assert exchange.patient_message.content == "差不多有三年了。"
    call = session.model_calls.get(patient_message__isnull=False)
    assert call.status == ModelCallStatus.FAILED
    assert call.error_code == "response_not_conversational"
    assert call.prompt_version == "patient-answer-v4"


@pytest.mark.django_db
def test_unrelated_question_uses_system_default_response_after_empty_route():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session

    exchange = ask_patient(
        session=session,
        student=student,
        content="你今天坐什么交通工具来的？",
        client_message_id="unrelated_question_01",
    )

    assert (
        exchange.patient_message.content
        == "这个我不太清楚。要不我们还是聊聊我这次口腔不舒服的情况吧。"
    )
    assert session.model_calls.filter(prompt_version="patient-route-v2").count() == 1
    answer_call = session.model_calls.get(patient_message__isnull=False)
    assert answer_call.provider == "rules"
    assert answer_call.model == "unknown-fact-policy-v2"
    assert answer_call.matched_fact_codes == []


@pytest.mark.django_db
def test_physical_exam_request_releases_once_reopens_and_is_traceably_scored():
    _, student, assignment = make_exam_data(suffix="9")
    session = start_session(assignment=assignment, student=student).session
    client = APIClient()
    client.force_authenticate(student)

    before = client.get(reverse("student-session-detail", kwargs={"session_id": session.id}))
    assert before.status_code == 200
    assert before.json()["physical_exam_result"] is None

    first = ask_patient(
        session=session,
        student=student,
        content="可以让我检查一下您的口腔吗？",
        client_message_id="physical_exam_request_01",
    )
    assert first.interaction_type == "physical_exam_released"
    assert first.patient_message.content == "可以，麻烦您检查吧。"
    assert first.patient_message.kind == MessageKind.PHYSICAL_EXAM_CONSENT
    release = PhysicalExamRelease.objects.get(session=session)
    assert release.trigger_message.content == "可以让我检查一下您的口腔吗？"
    assert release.result_message.kind == MessageKind.PHYSICAL_EXAM_RESULT
    assert release.result_message.role == MessageRole.SYSTEM
    assert release.result_message.content == "全口牙龈红肿，探诊易出血。"
    route_call = session.model_calls.get(prompt_version="patient-route-v2")
    assert route_call.routed_intent == "physical_exam_request"
    assert float(route_call.route_confidence) == 1.0
    assert session.model_calls.filter(prompt_version="patient-answer-v4").count() == 0

    visible = client.get(reverse("student-session-detail", kwargs={"session_id": session.id}))
    assert visible.json()["physical_exam_result"]["access_reason"] == "triggered"
    assert visible.json()["physical_exam_result"]["findings_text"] == release.result_message.content

    second = ask_patient(
        session=session,
        student=student,
        content="我想再检查一下您的口腔。",
        client_message_id="physical_exam_request_02",
    )
    assert second.interaction_type == "physical_exam_reopened"
    assert second.patient_message.content == "刚才已经检查过了，您可以再查看检查结果。"
    assert PhysicalExamRelease.objects.filter(session=session).count() == 1
    assert session.messages.filter(kind=MessageKind.PHYSICAL_EXAM_RESULT).count() == 1

    class CapturingGateway(PatientGateway):
        def __init__(self):
            self.history = []

        def route(
            self,
            *,
            question,
            facts,
            history,
            physical_exam_available=False,
        ):
            del question, facts, physical_exam_available
            self.history = history
            return RoutingResult(
                fact_codes=["history.duration"],
                confidence=1.0,
                provider="test",
                model="capturing-router",
                latency_ms=1,
            )

        def answer(self, *, question, facts, history, patient_prompt):
            del question, history, patient_prompt
            return GatewayResult(
                answer="差不多三年了。",
                fact_codes=[facts[0].code],
                provider="test",
                model="capturing-patient",
                latency_ms=1,
            )

    capturing_gateway = CapturingGateway()
    ask_patient(
        session=session,
        student=student,
        content="牙龈疼了多久？",
        client_message_id="after_physical_exam_question_01",
        gateway=capturing_gateway,
    )
    assert release.result_message.content not in {
        item["content"] for item in capturing_gateway.history
    }

    scoring_item = ScoringItem(
        version=session.case_version,
        code="score.physical_exam",
        dimension="clinical",
        label="主动申请体格检查",
        max_score="1.00",
        evaluation_method="rule",
        matching_config={"source": "physical_exam_request"},
        display_order=99,
    )
    ScoringItem.objects.bulk_create([scoring_item])
    generate_assessment(session)
    result = session.score_results.get(code="score.physical_exam")
    assert result.automatic_score == 1
    assert result.decision == ScoreDecision.ACHIEVED
    assert result.evidence_message_ids == [
        str(release.trigger_message_id),
        str(release.consent_message_id),
        str(release.result_message_id),
    ]


@pytest.mark.django_db
def test_physical_exam_stays_hidden_when_not_requested_until_feedback_release():
    _, student, assignment = make_exam_data(suffix="9")
    session = start_session(assignment=assignment, student=student).session
    client = APIClient()
    client.force_authenticate(student)

    symptom_question = ask_patient(
        session=session,
        student=student,
        content="你自己能看到牙龈红肿吗？",
        client_message_id="self_observation_question_01",
    )
    assert symptom_question.interaction_type == "patient_answer"
    assert not PhysicalExamRelease.objects.filter(session=session).exists()
    assert client.get(
        reverse("student-session-detail", kwargs={"session_id": session.id})
    ).json()["physical_exam_result"] is None

    close_assignment(assignment=assignment)
    assignment.feedback_released_at = timezone.now()
    assignment.save(update_fields=["feedback_released_at", "updated_at"])
    after_feedback = client.get(
        reverse("student-session-detail", kwargs={"session_id": session.id})
    )
    assert after_feedback.json()["physical_exam_result"]["access_reason"] == "feedback"
    assert after_feedback.json()["physical_exam_result"]["findings_text"] == (
        "全口牙龈红肿，探诊易出血。"
    )


@pytest.mark.django_db
def test_physical_exam_asset_requires_the_authorized_session_release(
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    teacher, student, assignment = make_exam_data(suffix="9")
    session = start_session(assignment=assignment, student=student).session
    object_key = "physical-exam/aa/private.bin"
    stored_path = tmp_path / object_key
    stored_path.parent.mkdir(parents=True)
    stored_path.write_bytes(b"private physical exam attachment")
    stored_asset = StoredAsset.objects.create(
        object_key=object_key,
        original_name="检查附件.custom",
        content_type="application/x-custom",
        size_bytes=32,
        sha256="a" * 64,
        deidentified_confirmed=True,
        created_by=teacher,
    )
    link = PhysicalExamAsset(
        version=session.case_version,
        physical_exam=session.case_version.physical_exam,
        stored_asset=stored_asset,
        kind="attachment",
    )
    PhysicalExamAsset.objects.bulk_create([link])
    student_url = reverse(
        "student-session-physical-exam-asset-content",
        kwargs={"session_id": session.id, "asset_id": link.id},
    )

    client = APIClient()
    client.force_authenticate(student)
    assert client.get(student_url).status_code == 404
    ask_patient(
        session=session,
        student=student,
        content="请允许我检查一下您的口腔。",
        client_message_id="physical_exam_asset_request_01",
    )
    content = client.get(student_url)
    assert content.status_code == 200
    assert content["Content-Type"] == "application/octet-stream"
    assert "attachment;" in content["Content-Disposition"]

    outsider = make_user("13700000009", RoleCode.STUDENT)
    client.force_authenticate(outsider)
    assert client.get(student_url).status_code == 404

    client.force_authenticate(teacher)
    teacher_content = client.get(
        reverse(
            "teacher-session-physical-exam-asset-content",
            kwargs={"session_id": session.id, "asset_id": link.id},
        )
    )
    assert teacher_content.status_code == 200


@pytest.mark.django_db
def test_case_draft_is_versioned_and_final_record_locks_further_patient_questions():
    _, student, assignment = make_exam_data(suffix="5")
    session = start_session(assignment=assignment, student=student).session

    updated = save_case_draft(
        session=session,
        student=student,
        case_draft=case_record_payload(correct=True),
        expected_revision=0,
    )
    assert updated.case_draft_revision == 1
    with pytest.raises(CaseDraftConflictError):
        save_case_draft(
            session=session,
            student=student,
            case_draft=case_record_payload(correct=False),
            expected_revision=0,
        )

    result = complete_session(
        session=session,
        student=student,
        case_record=case_record_payload(correct=True),
        expected_revision=1,
    )
    session.refresh_from_db()
    assert session.stage == SessionStage.COMPLETED
    assert result.submission.submission_type == SubmissionType.CASE_RECORD

    with pytest.raises(SessionLockedError):
        ask_patient(
            session=session,
            student=student,
            content="还有别的不舒服吗？",
            client_message_id="question_0003",
        )
    result.submission.payload = {"summary": "覆盖"}
    with pytest.raises(ValidationError):
        result.submission.save()


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
    payload = {"content": "牙龈疼痛有多久？", "client_message_id": "api_question_0001"}
    first = client.post(message_url, payload, format="json")
    second = client.post(message_url, payload, format="json")

    assert first.status_code == 200
    assert first.json()["patient_message"]["content"] == "差不多有三年了。"
    assert second.status_code == 200
    assert second.json()["reused"] is True
    assert second.json()["patient_message"]["id"] == first.json()["patient_message"]["id"]


@pytest.mark.django_db
def test_student_draft_and_completion_api_are_versioned_and_idempotent():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session
    client = APIClient()
    client.force_authenticate(student)
    draft_url = reverse("student-session-draft", kwargs={"session_id": session.id})
    complete_url = reverse("student-session-complete", kwargs={"session_id": session.id})
    payload = case_record_payload(correct=True)

    saved = client.patch(
        draft_url,
        {"expected_revision": 0, "case_draft": payload},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.json() == {"case_draft": payload, "case_draft_revision": 1}

    conflict = client.patch(
        draft_url,
        {"expected_revision": 0, "case_draft": case_record_payload(correct=False)},
        format="json",
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "case_draft_conflict"

    ask_patient(
        session=session,
        student=student,
        content="请允许我检查一下您的口腔。",
        client_message_id="complete_exam_request_01",
    )
    submitted_payload = {**payload, "specialty_exam": "客户端伪造的检查结果"}
    completed = client.post(
        complete_url,
        {"expected_revision": 1, "case_record": submitted_payload},
        format="json",
    )
    assert completed.status_code == 201
    assert completed.json()["reused"] is False
    record = completed.json()["session"]["case_record"]
    assert record["specialty_exam"] == "全口牙龈红肿，探诊易出血。"
    assert record["diagnosis"] == payload["diagnosis"]
    assert completed.json()["session"]["case_draft_revision"] == 2

    repeated = client.post(
        complete_url,
        {"expected_revision": 1, "case_record": submitted_payload},
        format="json",
    )
    assert repeated.status_code == 200
    assert repeated.json()["reused"] is True
    session.refresh_from_db()
    assert session.submissions.filter(submission_type=SubmissionType.CASE_RECORD).count() == 1

    message = client.post(
        reverse("student-session-message", kwargs={"session_id": session.id}),
        {"content": "还能继续提问吗？", "client_message_id": "after_complete_01"},
        format="json",
    )
    assert message.status_code == 409
    assert message.json()["code"] == "session_locked"


@pytest.mark.django_db
def test_student_draft_api_enforces_owner_and_timeout():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session
    draft_url = reverse("student-session-draft", kwargs={"session_id": session.id})
    payload = {"expected_revision": 0, "case_draft": case_record_payload(correct=True)}
    client = APIClient()

    outsider = make_user("13888888880", RoleCode.STUDENT)
    client.force_authenticate(outsider)
    assert client.patch(draft_url, payload, format="json").status_code == 404

    now = timezone.now()
    type(session).objects.filter(pk=session.pk).update(
        started_at=now - timedelta(minutes=2),
        deadline_at=now - timedelta(minutes=1),
    )
    client.force_authenticate(student)
    expired = client.patch(draft_url, payload, format="json")
    assert expired.status_code == 409
    assert expired.json()["code"] == "session_expired"
    session.refresh_from_db()
    assert session.status == SessionStatus.EXPIRED


@pytest.mark.django_db
def test_completion_api_waits_for_patient_answer():
    _, student, assignment = make_exam_data(suffix="0")
    session = start_session(assignment=assignment, student=student).session
    Message.objects.create(
        session=session,
        sequence=1,
        role=MessageRole.STUDENT,
        content="仍在等待回答的问题",
        client_message_id="api_processing_question_01",
        response_status=ResponseStatus.PROCESSING,
    )
    client = APIClient()
    client.force_authenticate(student)
    response = client.post(
        reverse("student-session-complete", kwargs={"session_id": session.id}),
        {"expected_revision": 0, "case_record": case_record_payload(correct=True)},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "session_locked"
    assert "正在生成" in response.json()["detail"]
    session.refresh_from_db()
    assert session.status == SessionStatus.ACTIVE
    assert session.submissions.count() == 0

    session.messages.filter(role=MessageRole.STUDENT).update(
        response_status=ResponseStatus.COMPLETED
    )
    blank_record = {field: "" for field in case_record_payload(correct=True)}
    allowed = client.post(
        reverse("student-session-complete", kwargs={"session_id": session.id}),
        {"expected_revision": 0, "case_record": blank_record},
        format="json",
    )
    assert allowed.status_code == 201
    assert allowed.json()["session"]["case_record"]["diagnosis"] == ""


@pytest.mark.django_db
def test_assignment_options_only_include_teachers_published_cases_and_classes():
    teacher, _, assignment = make_exam_data(suffix="0")
    draft = assignment.case_version.case.versions.get(status=VersionStatus.DRAFT)
    update_draft(
        draft=draft,
        data={"title_internal": "牙龈疼痛标准病例（更新）"},
    )
    latest_version = publish_draft(draft=draft, user=teacher).version
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.get(reverse("teacher-assignment-options"))

    assert response.status_code == 200
    assert response.json()["case_versions"] == [
        {
            "id": str(latest_version.id),
            "case_code": assignment.case_version.case.code,
            "title": "牙龈疼痛标准病例（更新）",
            "version_number": 2,
            "suggested_duration_minutes": 20,
        }
    ]
    assert response.json()["class_groups"][0]["id"] == str(assignment.class_group_id)
    assert response.json()["class_groups"][0]["student_count"] == 1

    stale_assignment = client.post(
        reverse("teacher-assignment-list"),
        {
            "title": "旧版本任务",
            "case_version_id": str(assignment.case_version_id),
            "class_group_id": str(assignment.class_group_id),
            "duration_minutes": 20,
            "opens_at": timezone.now(),
            "deadline_at": timezone.now() + timedelta(days=1),
        },
        format="json",
    )
    assert stale_assignment.status_code == 403
    assert "最新发布版本" in stale_assignment.json()["detail"]

    PhysicalExam.objects.filter(version=latest_version).update(findings_text=" \n ")
    unavailable = client.get(reverse("teacher-assignment-options"))
    assert unavailable.status_code == 200
    assert unavailable.json()["case_versions"] == []


def case_record_payload(*, correct: bool):
    answer = "未明确判断"
    return {
        "chief_complaint": "牙龈疼痛已有三年" if correct else answer,
        "present_illness": "牙龈疼痛反复发作" if correct else answer,
        "past_history": "无特殊" if correct else answer,
        "family_history": "无特殊" if correct else answer,
        "diagnosis": "考虑牙周组织疾病，最终诊断为慢性牙周炎" if correct else answer,
        "treatment": "申请牙周探诊" if correct else answer,
        "medical_advice": "定期复诊" if correct else answer,
    }


def complete_scored_session(*, session, student, correct: bool):
    if correct:
        ask_patient(
            session=session,
            student=student,
            content="牙龈疼痛有多久了？",
            client_message_id="scoring_question_01",
        )
    complete_session(
        session=session,
        student=student,
        case_record=case_record_payload(correct=correct),
        expected_revision=0,
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

    fact_result = session.score_results.get(code="score.history.duration")
    assert fact_result.decision == ScoreDecision.ACHIEVED
    assert len(fact_result.evidence_message_ids) == 2
    assert "牙龈疼痛有多久了" in fact_result.evidence_excerpt
    assert session.score_results.get(code="score.communication").decision == ScoreDecision.PENDING

    assessment.feedback_summary = "试图覆盖"
    with pytest.raises(ValidationError):
        assessment.save()


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
    assert record.json()["case_record"]["chief_complaint"] == "未明确判断"
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
    stale.refresh_from_db()
    assert stale.status == SessionStatus.EXPIRED
    assert stale.retention_expires_at == stale.completed_at + timedelta(days=180)


@pytest.mark.django_db
def test_session_cannot_finish_while_patient_answer_is_processing():
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

    with pytest.raises(SessionLockedError, match="正在生成"):
        complete_session(
            session=session,
            student=student,
            case_record=case_record_payload(correct=True),
            expected_revision=0,
        )
