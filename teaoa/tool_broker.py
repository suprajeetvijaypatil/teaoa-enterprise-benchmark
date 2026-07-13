from collections.abc import Callable
from typing import Any

from teaoa.policy import PolicyDecision, evaluate_action


def execute_governed_tool(
    tool_name: str,
    tool_function: Callable[..., Any],
    arguments: dict[str, Any],
    allowed_tools: list[str],
    forbidden_tools: list[str],
    risk_class: str,
    human_approval_required: bool,
) -> dict[str, Any]:
    """
    Check policy before executing a simulated enterprise tool.
    """

    decision = evaluate_action(
        tool_name=tool_name,
        allowed_tools=allowed_tools,
        forbidden_tools=forbidden_tools,
        risk_class=risk_class,
        human_approval_required=human_approval_required,
    )

    if decision == PolicyDecision.DENY:
        return {
            "status": "blocked",
            "tool": tool_name,
            "policy_decision": decision.value,
        }

    if decision == PolicyDecision.REQUIRE_APPROVAL:
        return {
            "status": "approval_required",
            "tool": tool_name,
            "policy_decision": decision.value,
        }

    try:
        result = tool_function(**arguments)

        return {
            "status": "success",
            "tool": tool_name,
            "policy_decision": decision.value,
            "result": result,
        }

    except Exception as error:
        return {
            "status": "tool_failure",
            "tool": tool_name,
            "policy_decision": decision.value,
            "error": str(error),
        }