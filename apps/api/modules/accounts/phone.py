import re

from django.core.exceptions import ValidationError

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
MAINLAND_PATTERN = re.compile(r"^1\d{10}$")


def normalize_phone(value: str) -> str:
    raw = str(value).strip()
    compact = re.sub(r"[\s()\-]", "", raw)

    if compact.startswith("0086"):
        compact = f"+86{compact[4:]}"
    elif MAINLAND_PATTERN.fullmatch(compact):
        compact = f"+86{compact}"
    elif compact.startswith("86") and MAINLAND_PATTERN.fullmatch(compact[2:]):
        compact = f"+{compact}"

    if not E164_PATTERN.fullmatch(compact):
        raise ValidationError("请输入有效的手机号码。")
    return compact


def validate_phone(value: str) -> None:
    normalize_phone(value)

