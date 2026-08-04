from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.cases.models import DiagnosisType, VersionStatus
from modules.cases.services import create_case_with_draft, publish_draft, update_draft
from modules.simulation.gateways import GatewayResult, PatientGateway
from modules.simulation.models import (
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
)
from modules.simulation.services import (
    AttemptAlreadyUsedError,
    StageLockedError,
    ask_patient,
    create_assignment,
    start_session,
    submit_stage,
)
from modules.teaching.models import ClassGroup, ClassMembership, Course, CourseTeacher

User = get_user_model()
PASSWORD = "MolarTraining!2026"


def make_user(phone: str, role_code: str):
    user = User.objects.create_user(phone=phone, password=PASSWORD, display_name=role_code)
    user.roles.add(Role.objects.get(code=role_code))
    return user


def make_exam_data(*, suffix="1"):
    teacher = make_user(f"1390000000{suffix}", RoleCode.TEACHER)
    student = make_user(f"1380000000{suffix}", RoleCode.STUDENT)
    case = create_case_with_draft(
        code=f"SIM-{suffix}",
        title_internal="牙龈疼痛标准病例",
        title_student="口腔不适病例",
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
    course = Course.objects.create(
        code=f"COURSE-{suffix}",
        name="口腔诊断学",
        created_by=teacher,
    )
    class_group = ClassGroup.objects.create(
        course=course,
        code=f"CLASS-{suffix}",
        name="第一教学班",
    )
    CourseTeacher.objects.create(course=course, teacher=teacher)
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
    assert response.json()[0]["case_title"] == "口腔不适病例"
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


class DiagnosisLeakingGateway(PatientGateway):
    def answer(self, *, question, facts):
        del question
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
    call = session.model_calls.get()
    assert call.status == ModelCallStatus.FAILED
    assert call.error_code == "response_validation_failed"


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
            "case_code": "SIM-0",
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
    assert record.json()["student_phone"] == student.phone
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
        "scored_maximum": 8.0,
        "maximum_score": 8.0,
        "provisional": False,
    }
    codes = [item["code"] for item in feedback.json()["scoring_items"]]
    assert "score.communication" not in codes
    assert "score.final" in codes
    assert feedback.json()["ai_feedback"] is None


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
