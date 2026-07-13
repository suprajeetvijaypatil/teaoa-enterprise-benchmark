from enum import Enum


class PolicyDecision(str, Enum):
    """Possible decisions returned by the TEAOA policy gateway."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


def evaluate_action(
    tool_name: str,
    allowed_tools: list[str],
    forbidden_tools: list[str],
    risk_class: str,
    human_approval_required: bool,
) -> PolicyDecision:
    """
    Decide whether a proposed tool action should be allowed,
    blocked, or sent for human approval.
    """

    if tool_name in forbidden_tools:
        return PolicyDecision.DENY

    if tool_name not in allowed_tools:
        return PolicyDecision.DENY

    if human_approval_required or risk_class == "high":
        return PolicyDecision.REQUIRE_APPROVAL

    return PolicyDecision.ALLOW