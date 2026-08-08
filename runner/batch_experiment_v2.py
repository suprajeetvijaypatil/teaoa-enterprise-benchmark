from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any

from runner.automatic_multi_turn_v2 import (
    run_automatic_loop,
)
from runner.benchmark_v2_loader import (
    load_scenario,
)
from runner.framework_adapter_registry_v2 import (
    ADAPTER_REGISTRY,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config(
    config_value: str,
) -> tuple[Path, dict[str, Any]]:
    config_path = Path(config_value)

    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    config_path = config_path.resolve()

    if not config_path.is_file():
        raise FileNotFoundError(
            f"Configuration file not found: "
            f"{config_path}"
        )

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        config = json.load(file)

    if not isinstance(config, dict):
        raise TypeError(
            "Experiment configuration must "
            "be a JSON object."
        )

    return config_path, config


def validate_string_list(
    config: dict[str, Any],
    field_name: str,
) -> list[str]:
    value = config.get(field_name)

    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(item, str)
            and item.strip()
            for item in value
        )
    ):
        raise ValueError(
            f"{field_name} must be a "
            "non-empty list of strings."
        )

    normalized = [
        item.strip()
        for item in value
    ]

    if len(normalized) != len(set(normalized)):
        raise ValueError(
            f"{field_name} contains duplicates."
        )

    return normalized


def validate_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    frameworks = validate_string_list(
        config,
        "frameworks",
    )

    configurations = validate_string_list(
        config,
        "configurations",
    )

    workflows = validate_string_list(
        config,
        "workflows",
    )

    unsupported_frameworks = sorted(
        framework
        for framework in frameworks
        if framework not in ADAPTER_REGISTRY
    )

    if unsupported_frameworks:
        raise ValueError(
            "Unsupported frameworks: "
            + ", ".join(
                unsupported_frameworks
            )
        )

    invalid_configurations = sorted(
        configuration
        for configuration in configurations
        if configuration not in {
            "native",
            "teaoa",
        }
    )

    if invalid_configurations:
        raise ValueError(
            "Invalid configurations: "
            + ", ".join(
                invalid_configurations
            )
        )

    repetitions = config.get(
        "repetitions",
        1,
    )

    if (
        not isinstance(repetitions, int)
        or repetitions < 1
    ):
        raise ValueError(
            "repetitions must be an integer "
            "of at least 1."
        )

    max_turns = config.get(
        "max_turns",
        0,
    )

    if (
        not isinstance(max_turns, int)
        or max_turns < 0
    ):
        raise ValueError(
            "max_turns must be a "
            "non-negative integer."
        )

    temperature = config.get(
        "temperature",
        0.0,
    )

    if not isinstance(
        temperature,
        (int, float),
    ):
        raise TypeError(
            "temperature must be numeric."
        )

    model = config.get("model")

    if (
        not isinstance(model, str)
        or not model.strip()
    ):
        raise ValueError(
            "model must be a non-empty string."
        )

    paid_execution = config.get(
        "paid_execution",
        False,
    )

    if not isinstance(
        paid_execution,
        bool,
    ):
        raise TypeError(
            "paid_execution must be true "
            "or false."
        )

    output_value = config.get(
        "output_directory",
        (
            "results/benchmark_v2/"
            "full_experiment"
        ),
    )

    if not isinstance(
        output_value,
        str,
    ):
        raise TypeError(
            "output_directory must be a string."
        )

    for workflow_id in workflows:
        load_scenario(workflow_id)

    return {
        **config,
        "frameworks": frameworks,
        "configurations": configurations,
        "workflows": workflows,
        "repetitions": repetitions,
        "max_turns": max_turns,
        "temperature": float(temperature),
        "model": model.strip(),
        "paid_execution": paid_execution,
        "output_directory": output_value,
    }


def build_matrix(
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    matrix = []

    combinations = product(
        config["workflows"],
        config["frameworks"],
        config["configurations"],
        range(
            1,
            config["repetitions"] + 1,
        ),
    )

    for (
        workflow_id,
        framework,
        configuration,
        repetition,
    ) in combinations:
        matrix.append(
            {
                "framework": framework,
                "workflow_id": workflow_id,
                "configuration": configuration,
                "repetition": repetition,
            }
        )

    return matrix

    return matrix


def resolve_output_root(
    config: dict[str, Any],
) -> Path:
    output_root = Path(
        config["output_directory"]
    )

    if not output_root.is_absolute():
        output_root = (
            PROJECT_ROOT / output_root
        )

    return output_root.resolve()


def build_result_path(
    output_root: Path,
    item: dict[str, Any],
) -> Path:
    filename = (
        f"{item['workflow_id'].lower()}_"
        f"{item['framework']}_"
        f"{item['configuration']}_"
        f"repeat_{item['repetition']:02d}.json"
    )

    return output_root / filename


def load_existing_status(
    result_path: Path,
) -> str | None:
    if not result_path.is_file():
        return None

    try:
        with result_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            existing = json.load(file)

        return existing.get("batch_status")

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


def save_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        ".json.tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            value,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_path.replace(path)


def run_paid_batch(
    config: dict[str, Any],
    matrix: list[dict[str, Any]],
    limit: int,
    stop_on_error: bool,
) -> dict[str, int]:
    output_root = resolve_output_root(
        config
    )

    counters = {
        "planned": len(matrix),
        "executed": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    }

    for item in matrix:
        result_path = build_result_path(
            output_root,
            item,
        )

        existing_status = (
            load_existing_status(result_path)
        )

        if existing_status == "completed":
            counters["skipped"] += 1
            continue

        if (
            limit > 0
            and counters["executed"] >= limit
        ):
            break

        print(
            "\nSTARTING RUN "
            f"{counters['executed'] + 1}: "
            f"{item['framework']} | "
            f"{item['workflow_id']} | "
            f"{item['configuration']} | "
            f"repeat {item['repetition']}"
        )

        counters["executed"] += 1

        try:
            result = run_automatic_loop(
                framework=item["framework"],
                workflow_id=item["workflow_id"],
                configuration=(
                    item["configuration"]
                ),
                model=config["model"],
                temperature=(
                    config["temperature"]
                ),
                max_turns=config["max_turns"],
            )

            record = {
                "batch_status": "completed",
                "batch_repetition": (
                    item["repetition"]
                ),
                "batch_saved_at_utc": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
                **result,
            }

            save_json(
                result_path,
                record,
            )

            counters["completed"] += 1

            print(
                "RUN SAVED: "
                f"{result_path}"
            )

        except Exception as error:
            counters["failed"] += 1

            failure_record = {
                "batch_status": "failed",
                "framework": item["framework"],
                "workflow_id": (
                    item["workflow_id"]
                ),
                "configuration": (
                    item["configuration"]
                ),
                "batch_repetition": (
                    item["repetition"]
                ),
                "failed_at_utc": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
                "error_type": (
                    type(error).__name__
                ),
                "error": str(error),
            }

            save_json(
                result_path,
                failure_record,
            )

            print(
                "RUN FAILED: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            if stop_on_error:
                raise

    return counters


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or execute a resumable "
            "benchmark_v2 experiment batch."
        )
    )

    parser.add_argument(
        "--config",
        required=True,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-paid-api-calls",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "Maximum new paid runs. "
            "Use 0 for the entire matrix."
        ),
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.limit < 0:
        raise ValueError(
            "--limit cannot be negative."
        )

    if (
        args.dry_run
        and args.confirm_paid_api_calls
    ):
        raise ValueError(
            "Choose only one execution mode."
        )

    config_path, raw_config = load_config(
        args.config
    )

    config = validate_config(
        raw_config
    )

    matrix = build_matrix(config)

    print(
        "\nBATCH EXPERIMENT PREFLIGHT\n"
    )

    print(f"Config: {config_path}")
    print(
        f"Frameworks: "
        f"{len(config['frameworks'])}"
    )
    print(
        f"Workflows: "
        f"{len(config['workflows'])}"
    )
    print(
        f"Configurations: "
        f"{len(config['configurations'])}"
    )
    print(
        f"Repetitions: "
        f"{config['repetitions']}"
    )
    print(
        f"Total planned runs: "
        f"{len(matrix)}"
    )
    print(
        f"Paid execution enabled: "
        f"{config['paid_execution']}"
    )

    if args.dry_run:
        print(
            "\nBATCH PREFLIGHT PASSED — "
            "no API calls were made."
        )
        return

    if not args.confirm_paid_api_calls:
        raise RuntimeError(
            "Paid execution is locked. "
            "Run --dry-run first."
        )

    if not config["paid_execution"]:
        raise RuntimeError(
            "Paid execution is disabled in "
            "the configuration file."
        )

    print(
        "\nWARNING: PAID API EXECUTION "
        "IS STARTING.\n"
    )

    counters = run_paid_batch(
        config=config,
        matrix=matrix,
        limit=args.limit,
        stop_on_error=args.stop_on_error,
    )

    print(
        "\nBATCH EXECUTION SUMMARY\n"
    )

    for name, value in counters.items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()