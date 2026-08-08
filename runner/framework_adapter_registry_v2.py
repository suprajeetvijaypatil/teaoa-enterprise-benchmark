from __future__ import annotations

import argparse
import importlib
import json
from typing import Callable
from uuid import uuid4

from runner.benchmark_v2_loader import load_scenario
from runner.framework_adapter_contract_v2 import (
    AdapterRequest,
    AdapterResult,
)
from runner.model_context_v2 import build_model_context


ADAPTER_REGISTRY = {
    "langgraph": {
        "module": "frameworks.langgraph.adapter_v2",
        "function": "execute_langgraph",
    },
    "crewai": {
        "module": "frameworks.crewai.adapter_v2",
        "function": "execute_crewai",
    },
    "autogen": {
        "module": "frameworks.autogen.adapter_v2",
        "function": "execute_autogen",
    },
    "semantic_kernel": {
        "module": "frameworks.semantic_kernel.adapter_v2",
        "function": "execute_semantic_kernel",
    },
    "openai_agents": {
        "module": "frameworks.openai_agents.adapter_v2",
        "function": "execute_openai_agents",
    },
    "google_adk": {
        "module": "frameworks.google_adk.adapter_v2",
        "function": "execute_google_adk",
    },
}


def get_adapter(
    framework: str,
) -> Callable[..., AdapterResult]:
    if framework not in ADAPTER_REGISTRY:
        supported = ", ".join(sorted(ADAPTER_REGISTRY))

        raise ValueError(
            f"Unsupported framework: {framework}. "
            f"Supported frameworks: {supported}"
        )

    adapter_details = ADAPTER_REGISTRY[framework]

    module = importlib.import_module(
        adapter_details["module"]
    )

    adapter_function = getattr(
        module,
        adapter_details["function"],
        None,
    )

    if adapter_function is None:
        raise AttributeError(
            f"Adapter function "
            f"{adapter_details['function']} was not found in "
            f"{adapter_details['module']}."
        )

    return adapter_function


def dispatch_adapter(
    request: AdapterRequest,
    *,
    allow_api_call: bool = False,
) -> AdapterResult:
    request.validate()

    if not request.dry_run and not allow_api_call:
        raise RuntimeError(
            "REAL API EXECUTION IS LOCKED IN THE REGISTRY."
        )

    adapter = get_adapter(request.framework)

    result = adapter(
        request,
        allow_api_call=allow_api_call,
    )

    result.validate()
    return result


def build_dry_request(
    framework: str,
) -> AdapterRequest:
    scenario = load_scenario("CS-001")
    context = build_model_context(scenario)

    return AdapterRequest(
        run_id=f"registry-{framework}-{uuid4().hex[:8]}",
        framework=framework,
        workflow_id="CS-001",
        configuration="native",
        model="MODEL_NOT_CALLED_IN_DRY_RUN",
        temperature=0.0,
        model_context=context,
        dry_run=True,
    )


def validate_registry() -> list[dict]:
    results = []

    for framework in ADAPTER_REGISTRY:
        try:
            request = build_dry_request(framework)

            result = dispatch_adapter(
                request,
                allow_api_call=False,
            )

            valid = (
                result.framework == framework
                and result.final_status
                in {
                    "dry_run_passed",
                    "dry_run_validated",
                }
                and result.token_usage["total_tokens"] == 0
                and result.metadata.get(
                    "api_call_made"
                ) is False
            )

            results.append(
                {
                    "framework": framework,
                    "status": (
                        "VALID" if valid else "FAILED"
                    ),
                    "valid": valid,
                    "final_status": result.final_status,
                    "api_call_made": result.metadata.get(
                        "api_call_made"
                    ),
                    "total_tokens": result.token_usage[
                        "total_tokens"
                    ],
                    "error": "",
                }
            )

        except Exception as error:
            results.append(
                {
                    "framework": framework,
                    "status": "FAILED",
                    "valid": False,
                    "final_status": None,
                    "api_call_made": None,
                    "total_tokens": None,
                    "error": str(error),
                }
            )

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the benchmark_v2 framework "
            "adapter registry."
        )
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate every registered adapter safely.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.dry_run:
        raise RuntimeError(
            "Only --dry-run is currently permitted."
        )

    results = validate_registry()

    print("\nFRAMEWORK ADAPTER REGISTRY VALIDATION\n")

    for result in results:
        print(
            f"{result['framework']}: "
            f"{result['status']} "
            f"| API call: {result['api_call_made']} "
            f"| tokens: {result['total_tokens']}"
        )

        if result["error"]:
            print(f"  Error: {result['error']}")

    valid_count = sum(
        result["valid"] for result in results
    )

    print(
        f"\nValid registry adapters: "
        f"{valid_count}/{len(results)}"
    )

    print("NO API CALLS WERE MADE.")

    if valid_count != len(results):
        raise SystemExit(
            "One or more registry adapters failed."
        )


if __name__ == "__main__":
    main()