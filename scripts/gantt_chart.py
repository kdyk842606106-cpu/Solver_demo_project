#!/usr/bin/env python3
"""
Gantt chart generator for schedule results.

Usage:
    # From API response JSON file:
    python scripts/gantt_chart.py response.json

    # From API directly (requires running server):
    python scripts/gantt_chart.py --url http://localhost:8000/api/v1/solve \\
        --body '{"machine_id":1,"current_state_id":1,"target_state_id":2,"objective":"minimize_makespan"}'

    # Output to file instead of showing:
    python scripts/gantt_chart.py response.json -o gantt.png
"""

import argparse
import json
import sys
from pathlib import Path


def load_schedule(source: str, body: str | None = None) -> dict:
    """Load schedule data from file path or URL."""
    if source.startswith("http"):
        import httpx
        payload = json.loads(body) if body else {}
        resp = httpx.post(source, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    else:
        with open(source, encoding="utf-8") as f:
            return json.load(f)


def render_gantt(data: dict, output_path: str | None = None) -> None:
    """Render a Gantt chart from a solve API response."""
    try:
        import matplotlib
        if output_path:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("matplotlib is required: pip install matplotlib", file=sys.stderr)
        sys.exit(1)

    schedule = data.get("schedule")
    if schedule is None:
        print(f"No schedule in response (status={data.get('status')})", file=sys.stderr)
        sys.exit(1)

    tasks = schedule["tasks"]
    makespan = schedule["makespan"]
    parallel_groups = schedule.get("parallel_groups", [])

    # Color palette by operation code
    palette = [
        "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
        "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
    ]
    op_codes = sorted({t["op_code"] for t in tasks})
    color_map = {code: palette[i % len(palette)] for i, code in enumerate(op_codes)}

    # Sort tasks by start time, then step order
    tasks_sorted = sorted(tasks, key=lambda t: (t["start"], t["step"]))

    fig, ax = plt.subplots(figsize=(12, max(3, len(tasks_sorted) * 0.8 + 1)))

    y_labels = []
    for i, task in enumerate(tasks_sorted):
        y = len(tasks_sorted) - 1 - i
        duration = task["end"] - task["start"]
        color = color_map[task["op_code"]]

        # Bar
        ax.barh(y, duration, left=task["start"], height=0.5,
                color=color, edgecolor="white", linewidth=0.5)

        # Label inside bar
        label = f"{task['op_code']} ({duration}min)"
        ax.text(task["start"] + duration / 2, y, label,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color="white" if duration > 8 else "black")

        # Resource annotation
        res = task.get("resource", "—")
        ax.text(task["end"] + 0.5, y, res, va="center", fontsize=8, color="#666")

        y_labels.append(f"Step {task['step']}")

    # Axis setup
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(reversed(y_labels), fontsize=9)
    ax.set_xlabel("Time (min)", fontsize=11)
    ax.set_xlim(-1, makespan + 8)
    ax.set_title(
        f"Schedule Gantt Chart — makespan = {makespan} min",
        fontsize=13, fontweight="bold", pad=12,
    )

    # Grid
    ax.xaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    # Makespan line
    ax.axvline(x=makespan, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax.text(makespan + 0.3, len(tasks_sorted) - 0.3, f"makespan={makespan}",
            color="red", fontsize=8, va="top")

    # Legend
    handles = [mpatches.Patch(color=color_map[c], label=c) for c in op_codes]
    ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)

    # Parallel annotation
    if parallel_groups:
        group_str = ", ".join(str(g) for g in parallel_groups)
        ax.text(0.01, -0.08, f"Parallel groups: {group_str}",
                transform=ax.transAxes, fontsize=8, color="#888")

    plt.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Saved to {output_path}")
    else:
        plt.show()

    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Generate Gantt chart from schedule result")
    parser.add_argument("source", nargs="?", help="JSON file path or use --url")
    parser.add_argument("--url", help="API endpoint URL (POST)")
    parser.add_argument("--body", help="JSON request body (for --url)")
    parser.add_argument("-o", "--output", help="Output image path (png/pdf/svg)")
    args = parser.parse_args()

    source = args.url or args.source
    if source is None:
        parser.error("Provide a JSON file path or --url")

    data = load_schedule(source, body=args.body)
    render_gantt(data, output_path=args.output)


if __name__ == "__main__":
    main()
