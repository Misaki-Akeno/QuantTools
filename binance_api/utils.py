from decimal import Decimal
from typing import Any, Dict, Mapping


def stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def drop_none(params: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}
