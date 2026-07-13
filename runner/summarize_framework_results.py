from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from typing import Any
from runner.shared_experiment import PROJECT_ROOT

def load_records(framework: str) -> list[dict[str, Any]]:
    raw = PROJECT_ROOT / "results" / "raw"
    records: list[dict[str, Any]] = []
    for path in sorted(raw.glob(f"{framework}_*.json")):
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            continue
        record = json.loads(text)
        record["_filename"] = path.name
        records.append(record)
    return records

def main(framework: str) -> None:
    records = load_records(framework)
    if not records:
        raise RuntimeError(f"No raw results found for {framework}.")
    output_dir = PROJECT_ROOT / "results" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{framework}_pilot_results.csv"
    fields = [
        "filename", "framework", "configuration", "repeat_number", "task_id",
        "domain", "scenario", "risk_class", "proposed_tool", "policy_decision",
        "execution_status", "step_success", "sla_compliant",
        "unsafe_action_attempts", "unsafe_actions_executed",
        "governance_violations", "human_interventions", "tool_failures",
        "recovered_failures", "input_tokens", "output_tokens",
        "estimated_cost_usd", "model_latency_seconds", "total_latency_seconds",
    ]
    rows: list[dict[str, Any]] = []
    for record in records:
        execution = record.get("execution_result", {})
        rows.append({
            "filename": record["_filename"],
            "framework": record.get("framework"),
            "configuration": record.get("configuration"),
            "repeat_number": record.get("repeat_number"),
            "task_id": record.get("task_id"),
            "domain": record.get("domain"),
            "scenario": record.get("scenario"),
            "risk_class": record.get("risk_class"),
            "proposed_tool": record.get("proposed_tool"),
            "policy_decision": record.get("policy_decision"),
            "execution_status": execution.get("status"),
            "step_success": record.get("step_success"),
            "sla_compliant": record.get("sla_compliant"),
            "unsafe_action_attempts": record.get("unsafe_action_attempts", 0),
            "unsafe_actions_executed": record.get("unsafe_actions_executed", 0),
            "governance_violations": record.get("governance_violations", 0),
            "human_interventions": record.get("human_interventions", 0),
            "tool_failures": record.get("tool_failures", 0),
            "recovered_failures": record.get("recovered_failures", 0),
            "input_tokens": record.get("input_tokens", 0),
            "output_tokens": record.get("output_tokens", 0),
            "estimated_cost_usd": record.get("estimated_cost_usd", 0.0),
            "model_latency_seconds": record.get("model_latency_seconds", 0.0),
            "total_latency_seconds": record.get("total_latency_seconds", 0.0),
        })
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["configuration"])].append(row)
    print(f"{framework.upper()} PILOT SUMMARY")
    print("-" * 50)
    print(f"Total runs: {len(rows)}")
    print(f"Total estimated cost: ${sum(float(r['estimated_cost_usd']) for r in rows):.6f}")
    for configuration, items in sorted(grouped.items()):
        count = len(items)
        successes = sum(bool(item["step_success"]) for item in items)
        unsafe = sum(int(item["unsafe_actions_executed"]) for item in items)
        violations = sum(int(item["governance_violations"]) for item in items)
        avg_latency = sum(float(item["total_latency_seconds"]) for item in items) / count
        print()
        print(configuration.upper())
        print(f"Runs: {count}")
        print(f"Step success: {successes}/{count}")
        print(f"Unsafe executions: {unsafe}")
        print(f"Governance violations: {violations}")
        print(f"Average latency: {avg_latency:.4f}s")
    print()
    print(f"CSV saved to: {csv_path}")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", choices=["langgraph", "crewai", "autogen", "semantic_kernel"], required=True)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    main(args.framework)
