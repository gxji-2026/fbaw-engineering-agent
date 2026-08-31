#!/usr/bin/env python3
"""V4.2.5 persistent JSON-lines bridge for native DeepSeek Harness FBAW tools.

New in V4.2.5:
  1. Verified checkpoint cache:
     - loads a preserved >=50 dB checkpoint from JSON when compatible;
     - reconstructs the design;
     - re-verifies it with the current Python RF model before accepting the cache;
     - rebuilds and overwrites the cache if missing/stale/invalid.
  2. Graceful shutdown:
     - supports the internal __shutdown__ RPC;
     - writes a final session summary;
     - exits cleanly after the response is flushed.

stdout is JSONL protocol only. Human-readable engineering progress goes to stderr.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import traceback
from pathlib import Path

import numpy as np

import fbaw_engineering_agent_3Rx4_V4_3c_autonomous_core as core


CACHE_SCHEMA = 2
CHECKPOINT_ALGORITHM_ID = "preserved-50db-checkpoint-v1"
BRIDGE_VERSION = "V4.3c"


def design_from_dict(d: dict) -> core.CellwiseDesign:
    cells_dict = d["cells"]
    cells = []
    for i in range(1, 5):
        c = cells_dict[f"cell{i}"]
        cells.append(core.CellParams(
            L3_nH=float(c["L3_nH"]),
            L5_nH=float(c["L5_nH"]),
            C1_pF=float(c["C1_pF"]),
            L7a_nH=float(c["L7a_nH"]),
            L7b_nH=float(c["L7b_nH"]),
            L7c_nH=float(c["L7c_nH"]),
        ))
    return core.CellwiseDesign(
        cells=tuple(cells),
        L4_nH=float(d["L4_nH"]),
        L6_nH=float(d["L6_nH"]),
    )


class NativeFBAWSession:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.outdir = Path(args.outdir).expanduser().resolve()
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.cache_path = (
            Path(args.checkpoint_cache).expanduser().resolve()
            if args.checkpoint_cache
            else self.outdir / "v4_2_5_preserved_50db_checkpoint.json"
        )

        self.goal = core.AgentGoal(
            nominal_ripple_max_dB=args.goal_nominal_ripple,
            q80_cp40_ripple_max_dB=args.goal_q80_ripple,
            q60_cp60_ripple_max_dB=args.goal_q60_ripple,
            rejection_min_dB=args.goal_rejection,
        )
        self.low = core.maybe_fit(
            args.comsol_low, core.MBVD_SEEDS["LOW_6p22"],
            self.outdir, args.vsrc, args.verbose_fit,
        )
        self.high = core.maybe_fit(
            args.comsol_high, core.MBVD_SEEDS["HIGH_7p40"],
            self.outdir, args.vsrc, args.verbose_fit,
        )
        self.f_ghz = np.linspace(5.5, 8.4, args.freq_points)

        self.cache_status = "disabled" if args.no_checkpoint_cache else "miss"
        loaded = None if args.no_checkpoint_cache else self._load_verified_checkpoint_cache()
        if loaded is None:
            self.current, self.current_v = self._rebuild_preserved_50db_checkpoint()
            if not args.no_checkpoint_cache:
                self._write_checkpoint_cache(self.current, self.current_v)
                self.cache_status = "rebuilt"
        else:
            self.current, self.current_v = loaded
            self.cache_status = "verified_hit"

        self.initial = self.current
        self.initial_v = self.current_v
        self.history: list[dict] = []
        self.inspected = False
        self.realistic_probe_seen = False
        self.controlled_probe_seen = False

    def _cache_metadata(self) -> dict:
        # Cache compatibility is intentionally independent of the DSH/bridge
        # software version. The cached object is a Python-verified RF checkpoint,
        # so only numerical-model inputs and the checkpoint-construction algorithm
        # belong in the compatibility fingerprint.
        return {
            "schema": CACHE_SCHEMA,
            "checkpoint_algorithm_id": CHECKPOINT_ALGORITHM_ID,
            "freq_points": int(self.args.freq_points),
            "vsrc": float(self.args.vsrc),
            "comsol_low": str(self.args.comsol_low or ""),
            "comsol_high": str(self.args.comsol_high or ""),
        }

    def _cache_compatible(self, payload: dict) -> tuple[bool, str]:
        meta = payload.get("metadata") or {}
        expected = self._cache_metadata()

        # Native V4.3c+ stable format.
        if (
            meta.get("schema") == CACHE_SCHEMA
            and meta.get("checkpoint_algorithm_id") == CHECKPOINT_ALGORITHM_ID
        ):
            for k in ("freq_points", "vsrc", "comsol_low", "comsol_high"):
                if meta.get(k) != expected.get(k):
                    return False, f"fingerprint mismatch: {k}"
            return True, "stable_fingerprint"

        # Safe migration path for V4.2.5 / V4.3 schema-1 caches.
        # Those versions unnecessarily embedded bridge_version in cache identity.
        # Numerical compatibility is accepted only when all model inputs match;
        # the candidate checkpoint is then re-verified before use and rewritten
        # in the stable schema-2 format.
        if meta.get("schema") == 1:
            for k in ("freq_points", "vsrc", "comsol_low", "comsol_high"):
                if meta.get(k) != expected.get(k):
                    return False, f"legacy fingerprint mismatch: {k}"
            return True, "legacy_schema1_migratable"

        return False, "unsupported cache schema/fingerprint"

    def _load_verified_checkpoint_cache(self):
        if not self.cache_path.exists():
            print(f"[V4.3c bridge] checkpoint cache MISS: {self.cache_path}", file=sys.stderr)
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            compatible, compatibility_mode = self._cache_compatible(payload)
            if not compatible:
                print(
                    f"[V4.3c bridge] checkpoint cache STALE ({compatibility_mode}); rebuilding.",
                    file=sys.stderr,
                )
                return None
            design = design_from_dict(payload["design"])
            verified = core.verify_cellwise_extended(design, self.low, self.high, self.f_ghz)

            # The cache represents the preserved >=50 dB checkpoint, not the final
            # relaxed-rejection branch. Re-verify the property that justified caching.
            rejection_values = [
                verified[name][side]
                for name in ("nominal", "Q80_Cp40", "Q60_Cp60")
                for side in ("lower_stopband_min_rejection_dB", "upper_stopband_min_rejection_dB")
            ]
            if min(rejection_values) < 50.0:
                print(
                    f"[V4.3c bridge] checkpoint cache INVALID: min rejection="
                    f"{min(rejection_values):.6f} dB < 50 dB; rebuilding.",
                    file=sys.stderr,
                )
                return None

            if compatibility_mode == "legacy_schema1_migratable":
                print(
                    f"[V4.3c bridge] legacy checkpoint cache re-verified; migrating to stable fingerprint.",
                    file=sys.stderr,
                )
                self._write_checkpoint_cache(design, verified)

            print(
                f"[V4.3c bridge] checkpoint cache VERIFIED HIT "
                f"({compatibility_mode}): {self.cache_path}",
                file=sys.stderr,
            )
            return design, verified
        except Exception as exc:
            print(
                f"[V4.3c bridge] checkpoint cache read/verify failed "
                f"({type(exc).__name__}: {exc}); rebuilding.",
                file=sys.stderr,
            )
            return None

    def _write_checkpoint_cache(self, design, verified):
        payload = {
            "metadata": self._cache_metadata(),
            "design": design.to_dict(),
            "verified_metrics": core.jsonable(verified),
        }
        tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(core.jsonable(payload), indent=2), encoding="utf-8")
        os.replace(tmp, self.cache_path)
        print(f"[V4.3c bridge] checkpoint cache SAVED: {self.cache_path}", file=sys.stderr)

    def _rebuild_preserved_50db_checkpoint(self):
        print("[V4.3c bridge] rebuilding Python-verified >=50 dB checkpoint...", file=sys.stderr)
        start = core.make_uniform_cellwise_start()
        coarse_final, _, _, _ = core.cell_by_cell_nominal_optimize(start, self.low, self.high, self.f_ghz)
        fine_final, _, _ = core.fine_cyclic_nominal_trim(coarse_final, self.low, self.high, self.f_ghz)
        terminal_final, _, _ = core.final_terminal_trim(fine_final, self.low, self.high, self.f_ghz)
        nominal_final, _, _ = core.l6_directed_extension(terminal_final, self.low, self.high, self.f_ghz)
        _, _, robustness_history = core.q60_cell_by_cell_robustness_trim(
            nominal_final, self.low, self.high, self.f_ghz
        )
        (_, _, selected, _), _ = core.collect_and_select_balanced_checkpoint(
            nominal_final, robustness_history, self.low, self.high, self.f_ghz
        )
        recovery_final, _, _, _ = core.final_lower_stopband_recovery(
            selected, self.low, self.high, self.f_ghz
        )
        final, final_v, _, _ = core.final_last_micro_trim(
            recovery_final, self.low, self.high, self.f_ghz
        )
        final, final_v, _, _ = core.ultrafine_global_l4l6_closure(
            final, self.low, self.high, self.f_ghz
        )
        final, final_v, _, _, _ = core.ultramicro_l3_with_l4l6_compensation(
            final, self.low, self.high, self.f_ghz
        )
        print("[V4.3c bridge] checkpoint ready.", file=sys.stderr)
        return final, final_v

    def _policy_gate(self, tool: str) -> str | None:
        if tool != "inspect_verified_design" and not self.inspected:
            return (
                "Native DSH policy: inspect_verified_design must be called "
                "before any other engineering tool."
            )
        if self.args.native_stress_protocol:
            if (
                tool not in {"inspect_verified_design", "realistic_constraint_conflict_probe"}
                and not self.realistic_probe_seen
            ):
                return (
                    "Native DSH stress policy: realistic_constraint_conflict_probe "
                    "is required after inspection and before optimization/recovery/STOP."
                )
        return None

    def call(self, tool: str, arguments: dict) -> dict:
        denial = self._policy_gate(tool)
        if denial:
            return {
                "tool": tool,
                "accepted": False,
                "policy_denied": True,
                "reason": denial,
                "state": core.compact_agent_state(self.current_v, self.goal),
            }

        cur, cur_v, result, search_df = core.execute_engineering_tool(
            tool, arguments, self.current, self.current_v,
            self.low, self.high, self.f_ghz, self.goal,
        )
        self.current, self.current_v = cur, cur_v

        if tool == "inspect_verified_design":
            self.inspected = True
        elif tool == "realistic_constraint_conflict_probe":
            self.realistic_probe_seen = True
        elif tool == "controlled_failure_probe":
            self.controlled_probe_seen = True

        rec = {
            "step": len(self.history) + 1,
            "tool": tool,
            "arguments": arguments,
            "result": result,
            "evaluation_after": core.evaluate_agent_goal(self.current_v, self.goal),
        }
        self.history.append(rec)

        if search_df is not None and not search_df.empty:
            search_df.to_csv(
                self.outdir / f"native_dsh_search_step_{len(self.history):02d}.csv",
                index=False,
            )

        result = dict(result)
        result["native_dsh_bridge"] = {
            "version": BRIDGE_VERSION,
            "tool_call_index": len(self.history),
            "python_authority": True,
            "state_persisted_in_bridge": True,
            "checkpoint_cache_status": self.cache_status,
        }
        return result

    def summary(self) -> dict:
        ev = core.evaluate_agent_goal(self.current_v, self.goal)
        return {
            "version": BRIDGE_VERSION,
            "native_dsh": True,
            "checkpoint_cache_status": self.cache_status,
            "checkpoint_cache_path": str(self.cache_path),
            "goal": core.jsonable(core.asdict(self.goal)),
            "evaluation": core.jsonable(ev),
            "tool_sequence": [r["tool"] for r in self.history],
            "tool_calls": len(self.history),
            "rollback_count": sum(
                bool((r["result"] or {}).get("rollback")) for r in self.history
            ),
            "explicit_stop_seen": any(
                r["tool"] == "stop_if_satisfied" for r in self.history
            ),
            "final_parameters": self.current.to_dict(),
            "final_metrics": self.current_v,
        }

    def write_final_summary(self) -> Path:
        path = self.outdir / "V4_3c_AUTONOMOUS_DSH_SESSION_SUMMARY.json"
        path.write_text(
            json.dumps(core.jsonable(self.summary()), indent=2),
            encoding="utf-8",
        )
        return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="V4.2.5 persistent native-DSH FBAW tool bridge"
    )
    p.add_argument("--comsol-low")
    p.add_argument("--comsol-high")
    p.add_argument("--vsrc", type=float, default=5.0)
    p.add_argument("--freq-points", type=int, default=1001)
    p.add_argument("--outdir", default="fbaw_3Rx4_native_dsh_output")
    p.add_argument("--verbose-fit", action="store_true")
    p.add_argument("--goal-nominal-ripple", type=float, default=0.55)
    p.add_argument("--goal-q80-ripple", type=float, default=0.63)
    p.add_argument("--goal-q60-ripple", type=float, default=0.75)
    p.add_argument("--goal-rejection", type=float, default=45.0)
    p.add_argument("--checkpoint-cache")
    p.add_argument("--no-checkpoint-cache", action="store_true")
    p.add_argument("--native-stress-protocol", action="store_true", default=True)
    p.add_argument(
        "--no-native-stress-protocol",
        action="store_false",
        dest="native_stress_protocol",
    )
    return p.parse_args()


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(core.jsonable(obj), separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> int:
    args = parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        session = NativeFBAWSession(args)

    emit({
        "event": "ready",
        "version": BRIDGE_VERSION,
        "native_dsh_bridge": True,
        "checkpoint_cache_status": session.cache_status,
        "checkpoint_cache_path": str(session.cache_path),
    })

    shutdown_requested = False
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get("id")
            tool = str(req.get("tool", ""))
            arguments = req.get("arguments") or {}

            if tool == "__summary__":
                result = session.summary()
            elif tool == "__shutdown__":
                summary_path = session.write_final_summary()
                result = {
                    "shutdown": True,
                    "summary_path": str(summary_path),
                    "summary": session.summary(),
                }
                shutdown_requested = True
            else:
                with contextlib.redirect_stdout(sys.stderr):
                    result = session.call(tool, arguments)

            emit({"id": req_id, "ok": True, "result": result})

            if shutdown_requested:
                print(
                    "[V4.3c bridge] graceful shutdown acknowledged; exiting.",
                    file=sys.stderr,
                )
                break

        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            emit({
                "id": req_id,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
