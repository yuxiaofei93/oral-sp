from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode
from modules.accounts.permissions import IsStudent, IsTeacherOrAdministrator
from modules.cases.models import CaseVersion, VersionStatus
from modules.teaching.models import ClassGroup

from .ai_evaluation import AIEvaluationError, run_ai_evaluation
from .models import CaseAssignment, SessionAssessment, SimulationSession
from .reporting import assignment_csv, assignment_report
from .reviews import (
    TeacherReviewError,
    create_teacher_review,
    latest_ai_attempt,
    latest_ai_run,
    latest_review,
    score_summary,
)
from .scoring import generate_assessment
from .serializers import (
    AIEvaluationCreateSerializer,
    AIEvaluationRunSerializer,
    AskPatientSerializer,
    AssignmentCreateSerializer,
    AssignmentOptionSerializer,
    AssignmentStatisticsSerializer,
    ExchangeSerializer,
    FeedbackSerializer,
    SessionSerializer,
    StageSubmissionSerializer,
    StudentAssignmentSerializer,
    SubmissionCreateSerializer,
    TeacherAssignmentSerializer,
    TeacherResponseRowSerializer,
    TeacherReviewCreateSerializer,
    TeacherReviewSerializer,
    TeacherSessionRecordSerializer,
)
from .services import (
    AssignmentUnavailableError,
    AttemptAlreadyUsedError,
    DuplicateSubmissionError,
    FeedbackUnavailableError,
    ModelUnavailableError,
    SessionExpiredError,
    SimulationError,
    StageLockedError,
    ask_patient,
    close_assignment,
    create_assignment,
    feedback_for_session,
    refresh_session_status,
    release_feedback,
    start_session,
    submit_stage,
)


def simulation_error_response(error: SimulationError) -> Response:
    if isinstance(error, ModelUnavailableError):
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, (AssignmentUnavailableError, FeedbackUnavailableError)):
        response_status = status.HTTP_403_FORBIDDEN
    elif isinstance(
        error,
        (AttemptAlreadyUsedError, SessionExpiredError, StageLockedError, DuplicateSubmissionError),
    ):
        response_status = status.HTTP_409_CONFLICT
    else:
        response_status = status.HTTP_400_BAD_REQUEST
    return Response(
        {"detail": str(error), "code": error.code},
        status=response_status,
    )


def teacher_assignment_queryset(user):
    queryset = CaseAssignment.objects.select_related(
        "case_version",
        "class_group",
        "class_group__course",
    ).annotate(
        student_count=Count("student_links", distinct=True),
        session_count=Count("sessions", distinct=True),
        active_count=Count(
            "sessions",
            filter=Q(sessions__status="active"),
            distinct=True,
        ),
        submitted_count=Count(
            "sessions",
            filter=Q(sessions__status="completed"),
            distinct=True,
        ),
        expired_count=Count(
            "sessions",
            filter=Q(sessions__status="expired"),
            distinct=True,
        ),
    )
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(created_by=user)


def student_assignment_queryset(user):
    sessions = SimulationSession.objects.filter(student=user).only(
        "id",
        "assignment_id",
        "status",
    )
    return (
        CaseAssignment.objects.filter(student_links__student=user)
        .select_related("case_version")
        .prefetch_related(Prefetch("sessions", queryset=sessions, to_attr="student_sessions"))
        .distinct()
    )


def student_session_queryset(user):
    return (
        SimulationSession.objects.filter(student=user)
        .select_related(
            "assignment",
            "case_version",
            "case_version__patient_profile",
            "assessment",
        )
        .prefetch_related("messages", "submissions")
    )


def teacher_session_queryset(user):
    queryset = (
        SimulationSession.objects.select_related(
            "assignment",
            "student",
            "case_version",
            "case_version__patient_profile",
            "assessment",
        )
        .prefetch_related(
            "messages",
            "submissions",
            "score_results",
            "teacher_reviews__reviewer",
            "ai_evaluation_runs__results__score_result",
            "case_version__diagnosis_rules",
            "case_version__tests",
        )
    )
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(assignment__created_by=user)


class TeacherAssignmentListCreateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        assignments = teacher_assignment_queryset(request.user)
        return Response(TeacherAssignmentSerializer(assignments, many=True).data)

    def post(self, request):
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            assignment = create_assignment(user=request.user, **serializer.validated_data)
        except SimulationError as error:
            return simulation_error_response(error)
        assignment = teacher_assignment_queryset(request.user).get(pk=assignment.pk)
        return Response(
            TeacherAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


class TeacherAssignmentOptionView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        case_versions = CaseVersion.objects.filter(
            status=VersionStatus.PUBLISHED,
            case__is_active=True,
        ).select_related("case")
        class_groups = ClassGroup.objects.filter(
            is_active=True,
            course__is_active=True,
        ).select_related("course").annotate(student_count=Count("memberships", distinct=True))
        if not (request.user.is_superuser or request.user.has_role(RoleCode.ADMINISTRATOR)):
            case_versions = case_versions.filter(case__created_by=request.user)
            class_groups = class_groups.filter(
                course__teacher_links__teacher=request.user,
            ).distinct()

        data = {
            "case_versions": [
                {
                    "id": str(version.id),
                    "case_code": version.case.code,
                    "title": version.title_internal,
                    "version_number": version.version_number,
                    "suggested_duration_minutes": version.time_limit_minutes,
                }
                for version in case_versions.order_by("case__code", "-version_number")
            ],
            "class_groups": [
                {
                    "id": str(class_group.id),
                    "course_name": class_group.course.name,
                    "class_name": class_group.name,
                    "student_count": class_group.student_count,
                }
                for class_group in class_groups.order_by("course__code", "code")
            ],
        }
        return Response(AssignmentOptionSerializer(data).data)


class TeacherAssignmentCloseView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(
            teacher_assignment_queryset(request.user),
            pk=assignment_id,
        )
        close_assignment(assignment=assignment)
        refreshed = teacher_assignment_queryset(request.user).get(pk=assignment.pk)
        return Response(TeacherAssignmentSerializer(refreshed).data)


class TeacherAssignmentReleaseFeedbackView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(
            teacher_assignment_queryset(request.user),
            pk=assignment_id,
        )
        try:
            release_feedback(assignment=assignment)
        except SimulationError as error:
            return simulation_error_response(error)
        refreshed = teacher_assignment_queryset(request.user).get(pk=assignment.pk)
        return Response(TeacherAssignmentSerializer(refreshed).data)


class TeacherAssignmentResponseListView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request, assignment_id):
        assignment = get_object_or_404(
            teacher_assignment_queryset(request.user),
            pk=assignment_id,
        )
        sessions = {
            session.student_id: session
            for session in teacher_session_queryset(request.user).filter(assignment=assignment)
        }
        rows = []
        for link in assignment.student_links.select_related("student").order_by(
            "student__display_name",
            "student__email",
        ):
            session = sessions.get(link.student_id)
            assessment = None
            if session and session.status != "active":
                try:
                    assessment = session.assessment
                except SessionAssessment.DoesNotExist:
                    assessment = generate_assessment(session)
                    session._prefetched_objects_cache.pop("score_results", None)
            end_time = session.completed_at if session else None
            elapsed_seconds = None
            if session:
                end_time = end_time or timezone.now()
                elapsed_seconds = max(0, int((end_time - session.started_at).total_seconds()))
            rows.append(
                {
                    "student_id": link.student_id,
                    "display_name": link.student.display_name,
                    "email": link.student.email,
                    "attempt_status": session.status if session else "not_started",
                    "session_id": session.id if session else None,
                    "started_at": session.started_at if session else None,
                    "completed_at": session.completed_at if session else None,
                    "elapsed_seconds": elapsed_seconds,
                    "score": (
                        score_summary(
                            session,
                            review=latest_review(session),
                        )
                        if assessment
                        else None
                    ),
                }
            )
        return Response(TeacherResponseRowSerializer(rows, many=True).data)


class TeacherAssignmentStatisticsView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request, assignment_id):
        assignment = get_object_or_404(
            teacher_assignment_queryset(request.user),
            pk=assignment_id,
        )
        report = assignment_report(assignment)
        return Response(AssignmentStatisticsSerializer(report).data)


class TeacherAssignmentCsvExportView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request, assignment_id):
        assignment = get_object_or_404(
            teacher_assignment_queryset(request.user),
            pk=assignment_id,
        )
        response = HttpResponse(
            assignment_csv(assignment),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="assignment-{assignment.id}.csv"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class TeacherSessionRecordView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request, session_id):
        session = get_object_or_404(teacher_session_queryset(request.user), pk=session_id)
        if session.status != "active":
            generate_assessment(session)
            session = teacher_session_queryset(request.user).get(pk=session_id)
        review = latest_review(session)
        ai_run = latest_ai_run(session)
        return Response(
            TeacherSessionRecordSerializer(
                session,
                context={
                    "review": review,
                    "ai_run": ai_run,
                    "latest_ai_attempt": latest_ai_attempt(session),
                },
            ).data
        )


class TeacherSessionAIEvaluationView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def post(self, request, session_id):
        session = get_object_or_404(teacher_session_queryset(request.user), pk=session_id)
        serializer = AIEvaluationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = run_ai_evaluation(
                session=session,
                requested_by=request.user,
                **serializer.validated_data,
            )
        except AIEvaluationError as error:
            unavailable_codes = {
                "configuration_error",
                "connection_error",
                "model_not_configured",
                "unsupported_provider",
            }
            invalid_provider_output_codes = {
                "empty_response",
                "incomplete_ai_result",
                "invalid_ai_evidence",
                "invalid_ai_item",
                "invalid_ai_json",
                "invalid_ai_reason",
                "invalid_ai_score",
                "invalid_json",
                "invalid_response",
                "missing_ai_evidence",
                "output_truncated",
                "unexpected_gateway_error",
            }
            if error.code == "http_429":
                response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            elif error.code.startswith("http_"):
                response_status = status.HTTP_502_BAD_GATEWAY
            elif error.code in unavailable_codes:
                response_status = status.HTTP_503_SERVICE_UNAVAILABLE
            elif error.code in invalid_provider_output_codes:
                response_status = status.HTTP_502_BAD_GATEWAY
            else:
                response_status = status.HTTP_409_CONFLICT
            return Response(
                {"detail": str(error), "code": error.code},
                status=response_status,
            )
        return Response(
            AIEvaluationRunSerializer(result.run).data,
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class TeacherSessionReviewView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def post(self, request, session_id):
        session = get_object_or_404(teacher_session_queryset(request.user), pk=session_id)
        serializer = TeacherReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = create_teacher_review(
                session=session,
                reviewer=request.user,
                **serializer.validated_data,
            )
        except TeacherReviewError as error:
            return Response(
                {"detail": str(error), "code": error.code},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            TeacherReviewSerializer(result.review).data,
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class StudentAssignmentListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        return Response(
            StudentAssignmentSerializer(
                student_assignment_queryset(request.user),
                many=True,
            ).data
        )


class StudentSessionStartView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(
            student_assignment_queryset(request.user),
            pk=assignment_id,
        )
        try:
            result = start_session(assignment=assignment, student=request.user)
        except SimulationError as error:
            return simulation_error_response(error)
        session = student_session_queryset(request.user).get(pk=result.session.pk)
        return Response(
            {"created": result.created, "session": SessionSerializer(session).data},
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class StudentSessionDetailView(APIView):
    permission_classes = [IsStudent]

    def get(self, request, session_id):
        session = get_object_or_404(student_session_queryset(request.user), pk=session_id)
        # A read also materializes server-side expiry; the client timer is display-only.
        if session.status == "active":
            refresh_session_status(session=session, student=request.user)
            session = student_session_queryset(request.user).get(pk=session_id)
        return Response(SessionSerializer(session).data)


class StudentSessionMessageView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, session_id):
        session = get_object_or_404(student_session_queryset(request.user), pk=session_id)
        serializer = AskPatientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            exchange = ask_patient(
                session=session,
                student=request.user,
                **serializer.validated_data,
            )
        except SimulationError as error:
            return simulation_error_response(error)
        return Response(
            ExchangeSerializer(exchange).data,
            status=status.HTTP_200_OK if exchange.patient_message else status.HTTP_202_ACCEPTED,
        )


class StudentSessionSubmissionView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, session_id):
        session = get_object_or_404(student_session_queryset(request.user), pk=session_id)
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = submit_stage(
                session=session,
                student=request.user,
                **serializer.validated_data,
            )
        except SimulationError as error:
            return simulation_error_response(error)
        return Response(
            StageSubmissionSerializer(submission).data,
            status=status.HTTP_201_CREATED,
        )


class StudentSessionFeedbackView(APIView):
    permission_classes = [IsStudent]

    def get(self, request, session_id):
        session = get_object_or_404(student_session_queryset(request.user), pk=session_id)
        try:
            feedback = feedback_for_session(session=session, student=request.user)
        except SimulationError as error:
            return simulation_error_response(error)
        return Response(FeedbackSerializer(feedback).data)
