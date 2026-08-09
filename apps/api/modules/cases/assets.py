import hashlib
import os
import uuid
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import (
    CaseVersion,
    PhysicalExam,
    PhysicalExamAsset,
    PhysicalExamAssetKind,
    StoredAsset,
    VersionStatus,
)
from .services import DraftConflictError

MAX_ASSET_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


class AssetValidationError(Exception):
    pass


def _safe_original_name(name: str) -> str:
    normalized = Path(name or "attachment").name
    normalized = "".join(
        character for character in normalized if 31 < ord(character) != 127
    ).strip()
    return normalized[:255] or "attachment"


def _read_upload(uploaded_file) -> bytes:
    if uploaded_file.size > MAX_ASSET_BYTES:
        raise AssetValidationError("单个文件不能超过 10 MB。")
    content = b"".join(uploaded_file.chunks())
    if not content:
        raise AssetValidationError("不能上传空文件。")
    if len(content) > MAX_ASSET_BYTES:
        raise AssetValidationError("单个文件不能超过 10 MB。")
    return content


def _normalize_image(content: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(BytesIO(content)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise AssetValidationError("图片像素尺寸过大。")
            source.verify()
        with Image.open(BytesIO(content)) as source:
            image_format = (source.format or "").upper()
            if image_format not in IMAGE_FORMATS:
                raise AssetValidationError("图片仅支持 JPEG、PNG 或 WebP 格式。")
            image = ImageOps.exif_transpose(source)
            output = BytesIO()
            extension, content_type = IMAGE_FORMATS[image_format]
            if image_format == "JPEG":
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(output, format="JPEG", quality=92, optimize=True)
            elif image_format == "PNG":
                image.save(output, format="PNG", optimize=True)
            else:
                image.save(output, format="WEBP", quality=92, method=6)
            normalized = output.getvalue()
    except AssetValidationError:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as error:
        raise AssetValidationError("图片内容损坏或格式不受支持。") from error
    if len(normalized) > MAX_ASSET_BYTES:
        raise AssetValidationError("处理后的图片不能超过 10 MB。")
    return normalized, extension, content_type


def _store_bytes(content: bytes, extension: str) -> tuple[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"physical-exam/{digest[:2]}/{uuid.uuid4().hex}.{extension}"
    destination = Path(settings.MEDIA_ROOT) / object_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.tmp-{uuid.uuid4().hex}")
    temporary.write_bytes(content)
    os.replace(temporary, destination)
    return object_key, digest


def upload_physical_exam_asset(
    *,
    draft: CaseVersion,
    uploaded_file,
    kind: str,
    deidentified_confirmed: bool,
    expected_updated_at,
    user,
) -> PhysicalExamAsset:
    if not deidentified_confirmed:
        raise AssetValidationError("请先确认资料已获授权并完成脱敏。")
    content = _read_upload(uploaded_file)
    original_name = _safe_original_name(uploaded_file.name)
    if kind == PhysicalExamAssetKind.IMAGE:
        content, extension, content_type = _normalize_image(content)
    elif kind == PhysicalExamAssetKind.ATTACHMENT:
        extension = "bin"
        content_type = str(getattr(uploaded_file, "content_type", ""))[:160]
    else:
        raise AssetValidationError("未知的体格检查文件类型。")

    object_key = ""
    stored_asset = None
    try:
        with transaction.atomic():
            locked = CaseVersion.objects.select_for_update().get(
                pk=draft.pk,
                status=VersionStatus.DRAFT,
            )
            if expected_updated_at and locked.updated_at != expected_updated_at:
                raise DraftConflictError("病例草稿已被其他操作更新，请刷新后重试。")
            physical_exam, _ = PhysicalExam.objects.get_or_create(version=locked)
            object_key, digest = _store_bytes(content, extension)
            stored_asset = StoredAsset.objects.create(
                object_key=object_key,
                original_name=original_name,
                content_type=content_type,
                size_bytes=len(content),
                sha256=digest,
                deidentified_confirmed=True,
                created_by=user,
            )
            display_order = physical_exam.assets.filter(kind=kind).count()
            link = PhysicalExamAsset.objects.create(
                version=locked,
                physical_exam=physical_exam,
                stored_asset=stored_asset,
                kind=kind,
                display_order=display_order,
            )
            locked.updated_at = timezone.now()
            locked.save(update_fields=["updated_at"])
            return link
    except Exception:
        if object_key:
            (Path(settings.MEDIA_ROOT) / object_key).unlink(missing_ok=True)
        raise


def delete_physical_exam_asset(
    *,
    draft: CaseVersion,
    link: PhysicalExamAsset,
    expected_updated_at,
) -> None:
    object_key_to_delete = ""
    with transaction.atomic():
        locked = CaseVersion.objects.select_for_update().get(
            pk=draft.pk,
            status=VersionStatus.DRAFT,
        )
        if expected_updated_at and locked.updated_at != expected_updated_at:
            raise DraftConflictError("病例草稿已被其他操作更新，请刷新后重试。")
        locked_link = PhysicalExamAsset.objects.select_related("stored_asset").get(
            pk=link.pk,
            version=locked,
        )
        stored_asset = locked_link.stored_asset
        locked_link.delete()
        if not stored_asset.physical_exam_links.exists():
            object_key_to_delete = stored_asset.object_key
            stored_asset.delete()
        locked.updated_at = timezone.now()
        locked.save(update_fields=["updated_at"])
    if object_key_to_delete:
        (Path(settings.MEDIA_ROOT) / object_key_to_delete).unlink(missing_ok=True)


def asset_path(asset: StoredAsset) -> Path:
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / asset.object_key).resolve()
    if root not in path.parents:
        raise AssetValidationError("文件存储路径无效。")
    return path
