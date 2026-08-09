from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode
from modules.accounts.permissions import IsAdministrator, IsTeacherOrAdministrator

from .assets import (
    AssetValidationError,
    asset_path,
    delete_physical_exam_asset,
    upload_physical_exam_asset,
)
from .models import Case, CaseVersion, PhysicalExamAsset, VersionStatus
from .serializers import (
    CaseCreateSerializer,
    CaseDraftSerializer,
    CaseListSerializer,
    PatientPromptTemplateSerializer,
    PatientQuestionTemplateSerializer,
    PhysicalExamAssetDeleteSerializer,
    PhysicalExamAssetUploadSerializer,
    PublishedVersionSerializer,
)
from .services import (
    DraftConflictError,
    PublishValidationError,
    create_case_with_draft,
    get_patient_prompt_template,
    get_patient_question_template,
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


class TeacherPatientQuestionTemplateView(APIView):
    def get_permissions(self):
        permission_class = (
            IsAdministrator if self.request.method == "PATCH" else IsTeacherOrAdministrator
        )
        return [permission_class()]

    def get(self, request):
        return Response(
            PatientQuestionTemplateSerializer(get_patient_question_template()).data
        )

    def patch(self, request):
        template = get_patient_question_template()
        serializer = PatientQuestionTemplateSerializer(
            template,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(PatientQuestionTemplateSerializer(template).data)


class TeacherCaseDraftView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get_object(self, request, case_id) -> CaseVersion:
        case = get_object_or_404(case_queryset(request.user), pk=case_id)
        return get_object_or_404(
            CaseVersion.objects.select_related("case", "patient_profile").prefetch_related(
                "facts",
                "tests",
                "diagnosis_rules",
                "scoring_items",
                "physical_exam__assets__stored_asset",
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


class TeacherPhysicalExamAssetUploadView(TeacherCaseDraftView):
    def post(self, request, case_id):
        draft = self.get_object(request, case_id)
        serializer = PhysicalExamAssetUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            upload_physical_exam_asset(
                draft=draft,
                uploaded_file=serializer.validated_data["file"],
                kind=serializer.validated_data["kind"],
                deidentified_confirmed=serializer.validated_data[
                    "deidentified_confirmed"
                ],
                expected_updated_at=serializer.validated_data["expected_updated_at"],
                user=request.user,
            )
        except DraftConflictError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except AssetValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        refreshed = self.get_object(request, case_id)
        return Response(CaseDraftSerializer(refreshed).data, status=status.HTTP_201_CREATED)


class TeacherPhysicalExamAssetDeleteView(TeacherCaseDraftView):
    def delete(self, request, case_id, asset_id):
        draft = self.get_object(request, case_id)
        serializer = PhysicalExamAssetDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link = get_object_or_404(PhysicalExamAsset, pk=asset_id, version=draft)
        try:
            delete_physical_exam_asset(
                draft=draft,
                link=link,
                expected_updated_at=serializer.validated_data["expected_updated_at"],
            )
        except DraftConflictError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        refreshed = self.get_object(request, case_id)
        return Response(CaseDraftSerializer(refreshed).data)


class TeacherPhysicalExamAssetContentView(TeacherCaseDraftView):
    def get(self, request, case_id, asset_id):
        draft = self.get_object(request, case_id)
        link = get_object_or_404(
            PhysicalExamAsset.objects.select_related("stored_asset"),
            pk=asset_id,
            version=draft,
        )
        path = asset_path(link.stored_asset)
        if not path.is_file():
            raise Http404
        is_attachment = link.kind == "attachment"
        response = FileResponse(
            path.open("rb"),
            as_attachment=is_attachment,
            filename=link.stored_asset.original_name,
            content_type=(
                "application/octet-stream"
                if is_attachment
                else link.stored_asset.content_type
            ),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


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
