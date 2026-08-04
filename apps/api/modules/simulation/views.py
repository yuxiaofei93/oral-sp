from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode
from modules.accounts.permissions import IsStudent, IsTeacherOrAdministrator

from .models import CaseAssignment, SimulationSession
from .serializers import (
    AskPatientSerializer,
    AssignmentCreateSerializer,
    ExchangeSerializer,
    FeedbackSerializer,
    SessionSerializer,
    StageSubmissionSerializer,
    StudentAssignmentSerializer,
    SubmissionCreateSerializer,
    TeacherAssignmentSerializer,
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
    ).annotate(
        student_count=Count("student_links", distinct=True),
        submitted_count=Count(
            "sessions",
            filter=Q(sessions__status="completed"),
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
        )
        .prefetch_related("messages", "submissions")
    )


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
