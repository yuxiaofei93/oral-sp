from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode
from modules.accounts.permissions import IsTeacherOrAdministrator

from .models import Case, CaseVersion, VersionStatus
from .serializers import (
    CaseCreateSerializer,
    CaseDraftSerializer,
    CaseListSerializer,
    PatientPromptTemplateSerializer,
    PublishedVersionSerializer,
)
from .services import (
    DraftConflictError,
    PublishValidationError,
    create_case_with_draft,
    get_patient_prompt_template,
    publish_draft,
    update_draft,
)


def case_queryset(user):
    queryset = Case.objects.prefetch_related("versions")
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(created_by=user)


class TeacherCaseListCreateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        return Response(CaseListSerializer(case_queryset(request.user), many=True).data)

    def post(self, request):
        serializer = CaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = create_case_with_draft(user=request.user, **serializer.validated_data)
        draft = case.versions.get(status=VersionStatus.DRAFT)
        return Response(CaseDraftSerializer(draft).data, status=status.HTTP_201_CREATED)


class TeacherPatientPromptTemplateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        return Response(PatientPromptTemplateSerializer(get_patient_prompt_template()).data)

    def patch(self, request):
        template = get_patient_prompt_template()
        serializer = PatientPromptTemplateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(PatientPromptTemplateSerializer(template).data)


class TeacherCaseDraftView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get_object(self, request, case_id) -> CaseVersion:
        case = get_object_or_404(case_queryset(request.user), pk=case_id)
        return get_object_or_404(
            CaseVersion.objects.select_related("case", "patient_profile").prefetch_related(
                "facts", "tests", "diagnosis_rules", "scoring_items"
            ),
            case=case,
            status=VersionStatus.DRAFT,
        )

    def get(self, request, case_id):
        return Response(CaseDraftSerializer(self.get_object(request, case_id)).data)

    def patch(self, request, case_id):
        draft = self.get_object(request, case_id)
        serializer = CaseDraftSerializer(draft, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            update_draft(draft=draft, data=dict(serializer.validated_data))
        except DraftConflictError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        refreshed = self.get_object(request, case_id)
        return Response(CaseDraftSerializer(refreshed).data)


class TeacherCasePublishView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def post(self, request, case_id):
        case = get_object_or_404(case_queryset(request.user), pk=case_id)
        draft = get_object_or_404(CaseVersion, case=case, status=VersionStatus.DRAFT)
        try:
            result = publish_draft(draft=draft, user=request.user)
        except PublishValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "created": result.created,
                "version": PublishedVersionSerializer(result.version).data,
            },
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )
