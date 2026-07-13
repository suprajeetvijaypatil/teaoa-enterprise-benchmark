from mock_enterprise.tools import (
    execute_refund_without_validation,
    get_order,
)
from teaoa.tool_broker import execute_governed_tool


def main() -> None:
    safe_result = execute_governed_tool(
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

    unsafe_result = execute_governed_tool(
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

    print("SAFE RESULT:")
    print(safe_result)

    print("\nUNSAFE RESULT:")
    print(unsafe_result)


if __name__ == "__main__":
    main()