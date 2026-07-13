from __future__ import annotations
import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from autogen_core import AgentId, MessageContext, RoutedAgent, SingleThreadedAgentRuntime, message_handler
from runner.shared_experiment import build_record, execute_configuration, load_task, print_run_summary, request_tool_proposal, save_record

@dataclass
class ExperimentRequest:
    task_name: str
    configuration: str
    repeat_number: int

@dataclass
class ExperimentResponse:
    record: dict[str, Any]
    output_path: str

class ExperimentAgent(RoutedAgent):
    @message_handler
    async def handle_request(self, message: ExperimentRequest, ctx: MessageContext) -> ExperimentResponse:
        started = perf_counter()
        task = load_task(message.task_name)
        proposal = request_tool_proposal(task)
        execution = execute_configuration(task, proposal, message.configuration)
        record = build_record(
            "autogen", message.configuration, message.repeat_number,
            task, proposal, execution, perf_counter() - started,
        )
        path = save_record(record)
        return ExperimentResponse(record=record, output_path=str(path))

async def run_async(task_name: str, configuration: str, repeat: int) -> None:
    runtime = SingleThreadedAgentRuntime()
    await ExperimentAgent.register(runtime, "experiment_agent", lambda: ExperimentAgent("TEAOA pilot experiment agent"))
    runtime.start()
    response = await runtime.send_message(
        ExperimentRequest(task_name, configuration, repeat),
        AgentId("experiment_agent", "default"),
    )
    await runtime.stop_when_idle()
    print_run_summary(response.record, Path(response.output_path))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--configuration", choices=["native", "teaoa"], required=True)
    parser.add_argument("--repeat", type=int, required=True)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_async(args.task, args.configuration, args.repeat))
