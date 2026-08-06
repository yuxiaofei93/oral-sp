def normalize_email_identifier(value: str) -> str:
    return str(value).strip().casefold()
