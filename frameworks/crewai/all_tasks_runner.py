from __future__ import annotations
import argparse
from time import perf_counter
from typing import Any
from crewai.flow import Flow, listen, start
from pydantic import BaseModel, Field
from runner.shared_experiment import build_record, execute_configuration, load_task, print_run_summary, request_tool_proposal, save_record

class PilotFlowState(BaseModel):
    task_name: str = ""
    configuration: str = "native"
    repeat_number: int = 1
    started_at: float = 0.0
    task: dict[str, Any] = Field(default_factory=dict)
    proposal: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    record: dict[str, Any] = Field(default_factory=dict)

class CrewAIPilotFlow(Flow[PilotFlowState]):
    @start()
    def propose_action(self) -> None:
        self.state.task = load_task(self.state.task_name)
        self.state.proposal = request_tool_proposal(self.state.task)

    @listen(propose_action)
    def execute_action(self) -> None:
        self.state.execution = execute_configuration(self.state.task, self.state.proposal, self.state.configuration)

    @listen(execute_action)
    def finalize(self) -> str:
        self.state.record = build_record(
            "crewai", self.state.configuration, self.state.repeat_number,
            self.state.task, self.state.proposal, self.state.execution,
            perf_counter() - self.state.started_at,
        )
        path = save_record(self.state.record)
        print_run_summary(self.state.record, path)
        return str(path)

def run(task_name: str, configuration: str, repeat: int) -> None:
    flow = CrewAIPilotFlow()
    flow.state.task_name = task_name
    flow.state.configuration = configuration
    flow.state.repeat_number = repeat
    flow.state.started_at = perf_counter()
    flow.kickoff()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--configuration", choices=["native", "teaoa"], required=True)
    parser.add_argument("--repeat", type=int, required=True)
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run(args.task, args.configuration, args.repeat)
