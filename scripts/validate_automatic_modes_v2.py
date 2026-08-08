from __future__ import annotations

import json
from uuid import uuid4

from runner.automatic_multi_turn_v2 import (
    GLOBAL_TURN_SAFETY_CAP,
    resolve_turn_limit,
)
from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
)
from runner.framework_adapter_registry_v2 import (
    dispatch_adapter,
)
from runner.model_context_v2 import build_model_context


def validate_mode(
    configuration: str,
) -> dict:
    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)

    turn_limit = resolve_turn_limit(
        scenario,
        0,
    )

    request = AdapterRequest(
        run_id=(
            f"automatic-{configuration}-"
            f"{uuid4().hex[:8]}"
        ),
        framework="openai_agents",
        workflow_id="CS-001",
        configuration=configuration,
        model="MODEL_NOT_CALLED_IN_DRY_RUN",
        temperature=0.0,
        model_context=context,
        dry_run=True,
    )

    result = dispatch_adapter(
        request,
        allow_api_call=False,
    )

    valid = (
        result.metadata.get(
            "api_call_made"
        )
        is False
        and result.token_usage[
            "total_tokens"
        ]
        == 0
        and 1
        <= turn_limit
        <= GLOBAL_TURN_SAFETY_CAP
    )

    return {
        "configuration": configuration,
        "valid": valid,
        "turn_limit": turn_limit,
        "api_call_made": result.metadata.get(
            "api_call_made"
        ),
        "total_tokens": result.token_usage[
            "total_tokens"
        ],
    }


def main() -> None:
    results = [
        validate_mode("native"),
        validate_mode("teaoa"),
    ]

    print(json.dumps(results, indent=2))

    for result in results:
        status = (
            "VALID"
            if result["valid"]
            else "FAILED"
        )

        print(
            f"{result['configuration']}: "
            f"{status} "
            f"| turn limit: "
            f"{result['turn_limit']}"
        )

    if not all(
        result["valid"]
        for result in results
    ):
        raise SystemExit(
            "Automatic mode validation failed."
        )

    print(
        "AUTOMATIC NATIVE/TEAOA VALIDATION "
        "PASSED — no API calls were made."
    )


if __name__ == "__main__":
    main()