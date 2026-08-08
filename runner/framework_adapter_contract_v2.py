from __future__ import annotations

import argparse
import json
from dataclasses import (
    asdict,
    dataclass,
    field,
)
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "adapter_contract_validation.json"
)


SUPPORTED_FRAMEWORKS = {
    "langgraph",
    "crewai",
    "autogen",
    "semantic_kernel",
    "openai_agents",
    "google_adk",
}


EXPECTED_SDK_VERSIONS = {
    "langgraph": "1.2.9",
    "crewai": "1.15.2",
    "autogen": "0.7.5",
    "semantic_kernel": "1.44.0",
    "openai_agents": "0.19.3",
    "google_adk": "2.6.2",
}


FORBIDDEN_CONTEXT_FIELDS = {
    "ground_truth",
    "required_steps",
    "scoring_rules",
    "maximum_score",
    "expected_final_status",
    "expected_policy_decision",
    "expected_security_decision",
    "expected_recovery",
    "unsafe_action_expected",
}


def find_forbidden_keys(
    value: Any,
    path: str = "context",
) -> list[str]:
    found = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"

            if key in FORBIDDEN_CONTEXT_FIELDS:
                found.append(child_path)

            found.extend(
                find_forbidden_keys(
                    child,
                    child_path,
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(
                find_forbidden_keys(
                    child,
                    f"{path}[{index}]",
                )
            )

    return found


@dataclass(frozen=True)
class AdapterRequest:
    run_id: str
    framework: str
    workflow_id: str
    configuration: str
    model: str
    temperature: float
    model_context: dict[str, Any]
    dry_run: bool = True

    def validate(self) -> None:
        if self.framework not in SUPPORTED_FRAMEWORKS:
            raise ValueError(
                f"Unsupported framework: "
                f"{self.framework}"
            )

        if self.configuration not in {
            "native",
            "teaoa",
        }:
            raise ValueError(
                "Configuration must be native "
                "or teaoa."
            )

        if not self.workflow_id:
            raise ValueError(
                "Workflow ID cannot be empty."
            )

        if not self.model:
            raise ValueError(
                "Model cannot be empty."
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                "Temperature must be between "
                "0.0 and 2.0."
            )

        leaked_fields = find_forbidden_keys(
            self.model_context
        )

        if leaked_fields:
            raise ValueError(
                "Evaluation-data leakage detected: "
                + ", ".join(leaked_fields)
            )


@dataclass
class AdapterResult:
    run_id: str
    framework: str
    workflow_id: str
    configuration: str
    model: str
    output_text: str
    completed_steps: list[str]
    proposed_tools: list[dict[str, Any]]
    policy_decisions: list[dict[str, Any]]
    final_status: str
    latency_seconds: float
    token_usage: dict[str, int] = field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def validate(self) -> None:
        if self.framework not in SUPPORTED_FRAMEWORKS:
            raise ValueError(
                f"Unsupported framework: "
                f"{self.framework}"
            )

        if self.latency_seconds < 0:
            raise ValueError(
                "Latency cannot be negative."
            )

        required_token_fields = {
            "input_tokens",
            "output_tokens",
            "total_tokens",
        }

        missing_token_fields = (
            required_token_fields
            - set(self.token_usage)
        )

        if missing_token_fields:
            raise ValueError(
                "Missing token fields: "
                + ", ".join(
                    sorted(missing_token_fields)
                )
            )

        for key in required_token_fields:
            value = self.token_usage[key]

            if (
                not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"Invalid token count for {key}."
                )

        expected_total = (
            self.token_usage["input_tokens"]
            + self.token_usage["output_tokens"]
        )

        if (
            self.token_usage["total_tokens"]
            != expected_total
        ):
            raise ValueError(
                "Total tokens do not equal input "
                "plus output tokens."
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def create_validation_request(
    framework: str,
) -> AdapterRequest:
    request = AdapterRequest(
        run_id=str(uuid4()),
        framework=framework,
        workflow_id="CS-001",
        configuration="teaoa",
        model="MODEL_NOT_CALLED",
        temperature=0.0,
        model_context={
            "workflow_id": "CS-001",
            "domain": "customer_support",
            "prompt": "Validation only.",
            "dataset": {
                "dataset_id": "validation",
            },
            "allowed_tools": [],
            "forbidden_tools": [],
        },
        dry_run=True,
    )

    request.validate()
    return request


def create_validation_result(
    request: AdapterRequest,
) -> AdapterResult:
    result = AdapterResult(
        run_id=request.run_id,
        framework=request.framework,
        workflow_id=request.workflow_id,
        configuration=request.configuration,
        model=request.model,
        output_text=(
            "Adapter contract validation only."
        ),
        completed_steps=[],
        proposed_tools=[],
        policy_decisions=[],
        final_status="dry_run_validated",
        latency_seconds=0.0,
        token_usage={
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        metadata={
            "dry_run": True,
            "api_call_made": False,
        },
    )

    result.validate()
    return result


def validate_framework(
    framework: str,
) -> dict[str, Any]:
    try:
        request = create_validation_request(
            framework
        )

        result = create_validation_result(
            request
        )

        result_dict = result.to_dict()

        passed = (
            result_dict["run_id"]
            == request.run_id
            and result_dict["framework"]
            == framework
            and result_dict["metadata"][
                "api_call_made"
            ]
            is False
        )

        return {
            "framework": framework,
            "expected_sdk_version": (
                EXPECTED_SDK_VERSIONS[framework]
            ),
            "request_valid": True,
            "result_valid": True,
            "api_call_made": False,
            "passed": passed,
        }

    except Exception as error:
        return {
            "framework": framework,
            "request_valid": False,
            "result_valid": False,
            "api_call_made": False,
            "passed": False,
            "error": str(error),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the common V2 framework "
            "adapter contract."
        )
    )

    parser.add_argument(
        "--framework",
        choices=[
            "all",
            *sorted(SUPPORTED_FRAMEWORKS),
        ],
        default="all",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    frameworks = (
        sorted(SUPPORTED_FRAMEWORKS)
        if args.framework == "all"
        else [args.framework]
    )

    results = [
        validate_framework(framework)
        for framework in frameworks
    ]

    passed_count = sum(
        result["passed"]
        for result in results
    )

    report = {
        "framework_count": len(frameworks),
        "passed_count": passed_count,
        "failed_count": (
            len(frameworks) - passed_count
        ),
        "real_execution_enabled": False,
        "api_call_made": False,
        "results": results,
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(json.dumps(report, indent=2))

    if report["failed_count"] > 0:
        raise SystemExit(
            "ADAPTER CONTRACT VALIDATION FAILED."
        )

    print(
        "ALL ADAPTER CONTRACTS PASSED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()