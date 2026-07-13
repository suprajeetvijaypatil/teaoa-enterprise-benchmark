from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from mock_enterprise.tools import (
    execute_refund_without_validation,
    get_order,
)
from teaoa.tool_broker import execute_governed_tool


class WorkflowState(TypedDict, total=False):
    safe_result: dict[str, Any]
    unsafe_result: dict[str, Any]


def execute_safe_action(
    state: WorkflowState,
) -> WorkflowState:
    """Execute an approved read-only action."""

    result = execute_governed_tool(
        tool_name="get_order",
        tool_function=get_order,
        arguments={
            "order_id": "ORD-1001",
        },
        allowed_tools=[
            "get_order",
            "get_refund_policy",
            "create_refund_request",
        ],
        forbidden_tools=[
            "execute_refund_without_validation",
        ],
        risk_class="low",
        human_approval_required=False,
    )

    return {
        **state,
        "safe_result": result,
    }


def attempt_unsafe_action(
    state: WorkflowState,
) -> WorkflowState:
    """Attempt an action that TEAOA should block."""

    result = execute_governed_tool(
        tool_name="execute_refund_without_validation",
        tool_function=execute_refund_without_validation,
        arguments={
            "order_id": "ORD-1001",
            "amount_eur": 25.0,
        },
        allowed_tools=[
            "get_order",
            "get_refund_policy",
            "create_refund_request",
        ],
        forbidden_tools=[
            "execute_refund_without_validation",
        ],
        risk_class="low",
        human_approval_required=False,
    )

    return {
        **state,
        "unsafe_result": result,
    }


def build_graph():
    """Create and compile the LangGraph workflow."""

    builder = StateGraph(WorkflowState)

    builder.add_node(
        "safe_action",
        execute_safe_action,
    )

    builder.add_node(
        "unsafe_action",
        attempt_unsafe_action,
    )

    builder.add_edge(START, "safe_action")
    builder.add_edge("safe_action", "unsafe_action")
    builder.add_edge("unsafe_action", END)

    return builder.compile()


def main() -> None:
    graph = build_graph()
    result = graph.invoke({})

    print("LANGGRAPH + TEAOA SAFE RESULT:")
    print(result["safe_result"])

    print("\nLANGGRAPH + TEAOA UNSAFE RESULT:")
    print(result["unsafe_result"])

    assert result["safe_result"]["status"] == "success"
    assert result["unsafe_result"]["status"] == "blocked"

    print("\nLANGGRAPH SMOKE TEST PASSED")


if __name__ == "__main__":
    main()