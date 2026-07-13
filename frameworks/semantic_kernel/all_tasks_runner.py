from __future__ import annotations
import argparse
import asyncio
import json
from time import perf_counter
from typing import Any
from semantic_kernel import Kernel
from semantic_kernel.functions import kernel_function
from runner.shared_experiment import build_record, execute_configuration, load_task, print_run_summary, request_tool_proposal, save_record

class ExperimentPlugin:
    @kernel_function(name="propose_action", description="Select one first enterprise action using the shared model adapter.")
    def propose_action(self, task_json: str) -> str:
        return json.dumps(request_tool_proposal(json.loads(task_json)))

    @kernel_function(name="execute_action", description="Execute one native or TEAOA-governed simulated action.")
    def execute_action(self, task_json: str, proposal_json: str, configuration: str) -> str:
        task = json.loads(task_json)
        proposal = json.loads(proposal_json)
        return json.dumps(execute_configuration(task, proposal, configuration))

async def run_async(task_name: str, configuration: str, repeat: int) -> None:
    task = load_task(task_name)
    kernel = Kernel()
    kernel.add_plugin(ExperimentPlugin(), plugin_name="Experiment")
    started = perf_counter()
    proposal_result = await kernel.invoke(
        plugin_name="Experiment", function_name="propose_action",
        task_json=json.dumps(task),
    )
    proposal = json.loads(str(proposal_result))
    execution_result = await kernel.invoke(
        plugin_name="Experiment", function_name="execute_action",
        task_json=json.dumps(task), proposal_json=json.dumps(proposal),
        configuration=configuration,
    )
    execution: dict[str, Any] = json.loads(str(execution_result))
    record = build_record(
        "semantic_kernel", configuration, repeat, task, proposal, execution,
        perf_counter() - started,
    )
    path = save_record(record)
    print_run_summary(record, path)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--configuration", choices=["native", "teaoa"], required=True)
    parser.add_argument("--repeat", type=int, required=True)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_async(args.task, args.configuration, args.repeat))
