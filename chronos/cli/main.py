r"""
CHRONOS Interactive Terminal CLI (chronos-cli)
Interactive live dashboard, event stream inspector, and adversarial scenario runner.
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from typing import Optional

from chronos.clock.virtual_clock import VirtualClock
from chronos.engine.chronos_agent import ChronosAgent
from chronos.evaluation.harness import ReplayHarness
from chronos.evaluation.benchmarks import LatencyBenchmark


def print_banner():
    print(r"""
========================================================================
   ____ _   _ ____   ___  _   _  ___  ____  
  / ___| | | |  _ \ / _ \| \ | |/ _ \/ ___| 
 | |   | |_| | |_) | | | |  \| | | | \___ \ 
 | |___|  _  |  _ <| |_| | |\  | |_| |___) |
  \____|_| |_|_| \_\\___/|_| \_|\___/|____/ 
  TEMPORAL CONTROL PLANE FOR INTERRUPTIBLE AI AGENTS
========================================================================
""")


def run_interactive_cli():
    print_banner()
    clock = VirtualClock(initial_time=0.0, mode="realtime")
    agent = ChronosAgent(clock=clock)
    harness = ReplayHarness(agent=agent)

    print("[+] CHRONOS Control Plane Initialized.")
    print("Commands:")
    print("  user <text>        - Send user prompt / speech turn")
    print("  interrupt <text>   - Send mid-stream correction / interruption")
    print("  demo               - Run canonical Delhi -> Mumbai interruption demo")
    print("  benchmark          - Run 1,000-iteration microsecond latency benchmark")
    print("  state              - Display active snapshot DAG and commit status")
    print("  quit               - Exit CLI\n")

    while True:
        try:
            cmd_raw = input("chronos> ").strip()
            if not cmd_raw:
                continue
            parts = cmd_raw.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd in ("exit", "quit", "q"):
                print("Exiting CHRONOS CLI.")
                break
            elif cmd in ("user", "u"):
                if not arg:
                    print("Error: Specify message. e.g. 'user Book a flight to Delhi'")
                    continue
                res = agent.process_user_input(arg)
                print(f"[ACK / Turn Processed]: {json.dumps(res, indent=2)}")
            elif cmd in ("interrupt", "i"):
                if not arg:
                    print("Error: Specify correction. e.g. 'interrupt Actually make that Mumbai'")
                    continue
                res = agent.process_user_input(arg)
                print(f"[Interruption Handled]: {json.dumps(res, indent=2)}")
            elif cmd == "demo":
                print("[*] Running Hero Interruption Replay...")
                report = harness.run_default_demo_scenario()
                print(f"[✓ Demo Finished] Task Completed: {report.task_completed}, Safety Compliance: {report.safety_compliance_rate * 100}%")
            elif cmd == "benchmark":
                print("[*] Running 1,000 Iteration Latency Benchmark...")
                bench = LatencyBenchmark.run_full_benchmark(iterations=1000)
                print(json.dumps(bench.model_dump(), indent=2))
            elif cmd == "state":
                state = agent.get_state_summary()
                print(json.dumps(state, indent=2))
            else:
                print(f"Unknown command: {cmd}")
        except (KeyboardInterrupt, EOFError):
            break


def main():
    parser = argparse.ArgumentParser(description="CHRONOS Temporal Control Plane CLI")
    parser.add_argument("--demo", action="store_true", help="Run the hero demo scenario")
    parser.add_argument("--benchmark", action="store_true", help="Run microsecond latency benchmarks")
    args = parser.parse_args()

    if args.demo:
        clock = VirtualClock(initial_time=0.0, mode="realtime")
        agent = ChronosAgent(clock=clock)
        harness = ReplayHarness(agent=agent)
        report = harness.run_default_demo_scenario()
        print(f"Hero Demo Completed: Task Completed = {report.task_completed}, Safety Compliance = {report.safety_compliance_rate * 100}%")
    elif args.benchmark:
        bench = LatencyBenchmark.run_full_benchmark(iterations=1000)
        print(json.dumps(bench.model_dump(), indent=2))
    else:
        run_interactive_cli()


if __name__ == "__main__":
    main()
