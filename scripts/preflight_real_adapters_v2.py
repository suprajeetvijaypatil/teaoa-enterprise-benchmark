from __future__ import annotations

import importlib.util
import json
import os
from importlib.metadata import (
    PackageNotFoundError,
    version,
)
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REPORT_PATH = (
    PROJECT_ROOT
    / "results"
    / "benchmark_v2"
    / "real_adapter_preflight.json"
)


FRAMEWORKS = {
    "langgraph": {
        "module": "langgraph.graph",
        "distribution": "langgraph",
    },
    "crewai": {
        "module": "crewai",
        "distribution": "crewai",
    },
    "autogen": {
        "module": "autogen_agentchat",
        "distribution": "autogen-agentchat",
    },
    "semantic_kernel": {
        "module": "semantic_kernel",
        "distribution": "semantic-kernel",
    },
    "openai_agents": {
        "module": "agents",
        "distribution": "openai-agents",
    },
    "google_adk": {
        "module": "google.adk",
        "distribution": "google-adk",
    },
}


CREDENTIAL_KEYS = [
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
]


def module_available(
    module_name: str,
) -> bool:
    try:
        return (
            importlib.util.find_spec(module_name)
            is not None
        )

    except (
        ImportError,
        ModuleNotFoundError,
        AttributeError,
    ):
        return False


def package_version(
    distribution: str,
) -> str | None:
    try:
        return version(distribution)

    except PackageNotFoundError:
        return None


def read_dotenv_status() -> dict[str, bool]:
    dotenv_path = PROJECT_ROOT / ".env"

    status = {
        key: False
        for key in CREDENTIAL_KEYS
    }

    if not dotenv_path.is_file():
        return status

    for raw_line in dotenv_path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip().strip(
            "\"'"
        )

        if key not in status:
            continue

        placeholder_values = {
            "",
            "your_key_here",
            "replace_me",
            "none",
            "null",
        }

        status[key] = (
            value.lower()
            not in placeholder_values
        )

    return status


def credential_status() -> dict[str, bool]:
    dotenv_status = read_dotenv_status()

    return {
        key: bool(os.getenv(key))
        or dotenv_status[key]
        for key in CREDENTIAL_KEYS
    }


def inspect_framework(
    framework: str,
    settings: dict[str, str],
) -> dict[str, Any]:
    framework_root = (
        PROJECT_ROOT
        / "frameworks"
        / framework
    )

    original_runner = (
        framework_root
        / "all_tasks_runner.py"
    )

    v2_runner = (
        framework_root
        / "all_tasks_runner_v2.py"
    )

    return {
        "framework": framework,
        "sdk_module": settings["module"],
        "sdk_available": module_available(
            settings["module"]
        ),
        "distribution": settings[
            "distribution"
        ],
        "installed_version": package_version(
            settings["distribution"]
        ),
        "original_runner_exists": (
            original_runner.is_file()
        ),
        "v2_runner_exists": (
            v2_runner.is_file()
        ),
    }


def main() -> None:
    framework_results = [
        inspect_framework(
            framework,
            settings,
        )
        for framework, settings
        in FRAMEWORKS.items()
    ]

    credentials = credential_status()

    installed_sdk_count = sum(
        result["sdk_available"]
        for result in framework_results
    )

    v2_runner_count = sum(
        result["v2_runner_exists"]
        for result in framework_results
    )

    report = {
        "framework_count": len(FRAMEWORKS),
        "installed_sdk_count": (
            installed_sdk_count
        ),
        "v2_runner_count": v2_runner_count,
        "credentials_configured": (
            credentials
        ),
        "real_execution_enabled": False,
        "api_call_made": False,
        "frameworks": framework_results,
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

    print(
        "REAL-ADAPTER PREFLIGHT COMPLETED — "
        "no API call was made."
    )


if __name__ == "__main__":
    main()