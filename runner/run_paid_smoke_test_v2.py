from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import AdapterRequest
from runner.framework_adapter_registry_v2 import dispatch_adapter
from runner.model_context_v2 import build_model_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one controlled OpenAI paid smoke test."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without making an API call.",
    )

    parser.add_argument(
        "--confirm-paid-api-call",
        action="store_true",
        help="Explicitly authorize one paid API call.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run and args.confirm_paid_api_call:
        raise ValueError(
            "Choose either --dry-run or "
            "--confirm-paid-api-call, not both."
        )

    if not args.dry_run and not args.confirm_paid_api_call:
        raise RuntimeError(
            "Execution is locked. Use --dry-run first."
        )

    real_execution = args.confirm_paid_api_call

    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)

    run_id = (
        "paid-smoke"
        if real_execution
        else "dry-smoke"
    ) + f"-{uuid4().hex[:8]}"

    request = AdapterRequest(
        run_id=run_id,
        framework="openai_agents",
        workflow_id="CS-001",
        configuration="native",
        model="gpt-5.6-luna",
        temperature=0.0,
        model_context=context,
        dry_run=not real_execution,
    )

    result = dispatch_adapter(
        request,
        allow_api_call=real_execution,
    )

    output = {
        "test_type": (
            "paid_api_smoke_test"
            if real_execution
            else "smoke_test_dry_run"
        ),
        "executed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "framework": "openai_agents",
        "workflow_id": "CS-001",
        "configuration": "native",
        "repeat": 1,
        "model": "gpt-5.6-luna",
        "real_execution": real_execution,
        "result": result.to_dict(),
    }

    output_name = (
        "paid_smoke_test_result.json"
        if real_execution
        else "paid_smoke_test_dry_validation.json"
    )

    output_path = (
        PROJECT_ROOT
        / "results"
        / "benchmark_v2"
        / output_name
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(output, file, indent=2)

    print(json.dumps(output, indent=2))
    print(f"Report: {output_path}")

    if real_execution:
        print("PAID SMOKE TEST COMPLETED.")
    else:
        print(
            "SMOKE TEST CONFIGURATION PASSED — "
            "no API call was made."
        )


if __name__ == "__main__":
    main()