"""Static routing rules. Owned by the CX ops team, edited without review."""
from .models import Priority

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "billing": ("invoice", "refund", "charge", "결제", "환불"),
    "outage": ("down", "cannot login", "500", "장애", "접속안됨"),
    "how-to": ("how do i", "where is", "사용법"),
    "feedback": ("suggest", "feature request", "건의"),
}

ESCALATION_TENANTS = {"acme-corp", "globex", "initech"}

GROUP_BY_CATEGORY = {
    "billing": "cx-billing",
    "outage": "sre-oncall",
    "how-to": "cx-tier1",
    "feedback": "product",
    "unknown": "cx-tier1",
}

PRIORITY_FLOOR = {
    "outage": Priority.HIGH,
    "billing": Priority.NORMAL,
}
