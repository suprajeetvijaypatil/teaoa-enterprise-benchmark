from mock_enterprise.tools import (
    create_refund_request,
    get_order,
    get_refund_policy,
)


def main() -> None:
    order = get_order("ORD-1001")
    policy = get_refund_policy()

    refund = create_refund_request(
        order_id="ORD-1001",
        amount_eur=25.0,
        reason="Customer returned the product.",
    )

    print("ORDER:")
    print(order)

    print("\nPOLICY:")
    print(policy)

    print("\nREFUND REQUEST:")
    print(refund)


if __name__ == "__main__":
    main()