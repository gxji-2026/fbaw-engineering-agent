#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    p = argparse.ArgumentParser(description="Score V4.3c autonomous DSH FBAW benchmark.")
    p.add_argument(
        "--summary",
        default=r"D:\AI_Research\dsh-run\fbaw_3Rx4_native_dsh_output\V4_3c_AUTONOMOUS_DSH_SESSION_SUMMARY.json",
    )
    args = p.parse_args()
    path = Path(args.summary)
    if not path.exists():
        print("V4.3 benchmark summary not found:", path)
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    seq = list(data.get("tool_sequence") or [])
    ev = data.get("evaluation") or {}
    satisfied = bool(ev.get("satisfied"))
    rollback_count = int(data.get("rollback_count") or 0)
    explicit_stop = bool(data.get("explicit_stop_seen"))
    cache_status = data.get("checkpoint_cache_status")

    checks = {
        "summary_exists": True,
        "started_with_inspection": bool(seq and seq[0] == "inspect_verified_design"),
        "used_real_engineering_action": any(
            t in {"optimize_ripple", "recover_rejection"} for t in seq
        ),
        "handled_rollback_or_conflict": (
            rollback_count >= 1
            or "realistic_constraint_conflict_probe" in seq
            or "controlled_failure_probe" in seq
        ),
        "python_final_satisfied": satisfied,
        "explicit_python_authorized_stop": explicit_stop,
        "did_not_close_before_stop": (
            "close_engineering_session" not in seq
            or (
                "stop_if_satisfied" in seq
                and seq.index("stop_if_satisfied") < seq.index("close_engineering_session")
            )
        ),
    }

    score = sum(bool(v) for v in checks.values())
    total = len(checks)
    passed = all(checks.values())

    print("=" * 78)
    print("V4.3c AUTONOMOUS DSH FBAW BENCHMARK SCORE")
    print("=" * 78)
    print("tool_sequence:", " -> ".join(seq) if seq else "<none>")
    print("cache_status:", cache_status)
    print("rollback_count:", rollback_count)
    print("final_satisfied:", satisfied)
    print()
    for k, v in checks.items():
        print(f"{k:38s}: {'PASS' if v else 'FAIL'}")
    print()
    print(f"SCORE: {score}/{total}")
    print("OVERALL:", "PASS" if passed else "FAIL")
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
