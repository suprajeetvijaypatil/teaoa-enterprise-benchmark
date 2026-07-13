from __future__ import annotations
import argparse
from time import perf_counter
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph
from runner.shared_experiment import build_record, execute_configuration, load_task, print_run_summary, request_tool_proposal, save_record

class PilotState(TypedDict, total=False):
    task: dict[str, Any]
    proposal: dict[str, Any]
    execution: dict[str, Any]

def build_graph(configuration: str):
    def propose(state: PilotState) -> PilotState:
        return {**state, "proposal": request_tool_proposal(state["task"])}
    def execute(state: PilotState) -> PilotState:
        return {**state, "execution": execute_configuration(state["task"], state["proposal"], configuration)}
    builder = StateGraph(PilotState)
    builder.add_node("propose", propose)
    builder.add_node("execute", execute)
    builder.add_edge(START, "propose")
    builder.add_edge("propose", "execute")
    builder.add_edge("execute", END)
    return builder.compile()

def run(task_name: str, configuration: str, repeat: int) -> None:
    task = load_task(task_name)
    graph = build_graph(configuration)
    started = perf_counter()
    state = graph.invoke({"task": task})
    record = build_record("langgraph", configuration, repeat, task, state["proposal"], state["execution"], perf_counter() - started)
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
    run(args.task, args.configuration, args.repeat)
