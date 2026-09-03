#!/usr/bin/env python3
"""
fbaw_closed_loop_all_in_one.py

One-file closed-loop FBAW/DFR design framework — ADS-confirmed L6 placement:

COMSOL export -> double-motional MBVD fit -> DFR 3Rx4 circuit model
-> Pareto optimization -> Python-verified result
-> Cohere advisory -> local refinement proposal
-> Python re-verification -> final verified result

The LLM is advisory only. It never accepts its own numerical claims.
Every candidate proposed after the LLM step is re-simulated and ranked by Python.

Default FR3 target:
    passband = 6.425...7.125 GHz
    center   = 6.775 GHz
    synthesized TZ targets ~6.22 and 7.40 GHz

Default DFR 3Rx4 baseline used here:
    L3 = 0.269 nH
    L4 = 0.559 nH
    L5 = 0.180 nH
    L6 = 0.988 nH
    L7(total) = 0.7405 nH, implemented as three equal series segments (~0.246833 nH each)
    C1 = 0.7326 pF

Resonator seed MBVD values are the values shown in the supplied
6.22 GHz, 7.40 GHz, and 7.49 GHz ADS/MBVD schematics. If COMSOL
text exports are supplied, the script fits those data and replaces
the corresponding seed MBVD model.

Required packages:
    numpy pandas scipy matplotlib

Optional:
    cohere      # only for the advisory step

Examples
--------
1) Full Python run using the supplied MBVD seeds, no cloud LLM:
    python fbaw_closed_loop_all_in_one.py --no-llm

2) Use COMSOL exports for all three resonators:
    python fbaw_closed_loop_all_in_one.py ^
        --comsol-low 6p22.txt ^
        --comsol-high 7p40.txt ^
        --comsol-sfr 7p49.txt

3) Enable Cohere:
    set COHERE_API_KEY=...
    python fbaw_closed_loop_all_in_one.py

COMSOL text format
------------------
One header line followed by at least two tab/space-separated columns:
    frequency_GHz    log10(abs(I))

Important modeling note
-----------------------
The 3Rx4 Python network is a circuit-level surrogate of the supplied schematic.
Finite inductor Q is modeled by ESR = 2*pi*fref*L/Q.
Cp is distributed over the three L7 segment nodes as a configurable surrogate.
For sign-off, optionally compare the Python result with an exported ADS/EM .s2p.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None


# =============================================================================
# 0. PROJECT CONSTANTS
# =============================================================================

PASSBAND_GHZ = (6.425, 7.125)
CENTER_GHZ = 6.775
TZ_TARGETS_GHZ = (6.22, 7.40)

# Rejection reporting windows: exclude the transition skirts near the passband.
# These windows correspond to the flat far-stopband regions visible in the S21 plots.
LOW_STOP_GHZ = (5.50, 6.00)
HIGH_STOP_GHZ = (7.70, 8.40)

# Keep the former broad windows as separate transition/near-stop diagnostics.
LOW_NEAR_STOP_GHZ = (5.60, 6.30)
HIGH_NEAR_STOP_GHZ = (7.25, 8.20)

FREF_HZ = CENTER_GHZ * 1e9
Z0 = 50.0

DEFAULT_QIND = 60.0
DEFAULT_CP_FF = 60.0

# Revised 3Rx4 baseline.
BASELINE = {
    "L3_nH": 0.269,
    "L4_nH": 0.559,
    "L5_nH": 0.180,
    "L6_nH": 0.988,
    "L7_total_nH": 0.7405,
    "C1_pF": 0.7326,
}

# Search bounds are intentionally local and physically conservative.
BOUNDS = {
    "L3_nH": (0.255, 0.283),
    "L4_nH": (0.48, 0.68),
    "L5_nH": (0.170, 0.190),
    "L6_nH": (0.82, 1.16),
    "L7_total_nH": (0.70, 0.78),
    "C1_pF": (0.66, 0.82),
}


# Historical 3Rx4 checkpoint after nominal ripple-first matching trim.
ROBUST_START = {
    "L3_nH": 0.2690000000,
    "L4_nH": 0.623125324307486,
    "L5_nH": 0.1800000000,
    "L6_nH": 0.9394480911134965,
    "L7_total_nH": 0.7405000000,
    "C1_pF": 0.7718444377104999,
}

ROBUST_NOMINAL_RIPPLE_MAX_DB = 0.78
ROBUST_Q60_BW_MIN_GHZ = 0.80
ROBUST_TZ_TOL_GHZ = 0.020
BALANCED_RIPPLE_TARGET_DB = 1.00
BALANCED_IL_TARGET_DB = 1.27

# Reference embedded-impedance checkpoint from the prior synthesis workflow.
ZEMBED_622_OHM = complex(12.609, -47.499)


# =============================================================================
# 1. MBVD MODEL AND COMSOL -> MBVD FIT
# =============================================================================

@dataclass(frozen=True)
class MBVD:
    name: str
    Cm1_fF: float
    Lm1_nH: float
    Rm1_ohm: float
    Cm2_fF: float
    Lm2_nH: float
    Rm2_ohm: float
    C0_pF: float
    R0_ohm: float
    Rs_ohm: float
    residual_norm: float = float("nan")
    source: str = "seed"

    def as_fit_array(self) -> np.ndarray:
        return np.array([
            self.Cm1_fF, self.Lm1_nH, self.Rm1_ohm,
            self.Cm2_fF, self.Lm2_nH, self.Rm2_ohm,
            self.C0_pF, self.R0_ohm, self.Rs_ohm,
        ], dtype=float)

    @classmethod
    def from_fit_array(
        cls, name: str, x: Sequence[float], residual_norm: float, source: str
    ) -> "MBVD":
        return cls(name, *map(float, x), residual_norm=float(residual_norm), source=source)

    def z(self, f_hz: np.ndarray | float) -> np.ndarray:
        f = np.asarray(f_hz, dtype=float)
        w = 2 * np.pi * f
        cm1 = self.Cm1_fF * 1e-15
        lm1 = self.Lm1_nH * 1e-9
        cm2 = self.Cm2_fF * 1e-15
        lm2 = self.Lm2_nH * 1e-9
        c0 = self.C0_pF * 1e-12

        z1 = self.Rm1_ohm + 1j*w*lm1 + 1/(1j*w*cm1)
        z2 = self.Rm2_ohm + 1j*w*lm2 + 1/(1j*w*cm2)
        # The supplied ADS MBVD schematics show R0 and C0 in SERIES
        # as the third branch, in parallel with the two motional branches.
        z0 = self.R0_ohm + 1/(1j*w*c0)
        return self.Rs_ohm + 1/(1/z1 + 1/z2 + 1/z0)

    def branch_resonances_GHz(self) -> Tuple[float, float]:
        f1 = 1/(2*np.pi*np.sqrt(self.Lm1_nH*1e-9 * self.Cm1_fF*1e-15))
        f2 = 1/(2*np.pi*np.sqrt(self.Lm2_nH*1e-9 * self.Cm2_fF*1e-15))
        return float(f1/1e9), float(f2/1e9)


MBVD_SEEDS: Dict[str, MBVD] = {
    "LOW_6p22": MBVD(
        name="LOW_6p22",
        Cm1_fF=166.355, Lm1_nH=3.933, Rm1_ohm=0.072,
        Cm2_fF=25.309, Lm2_nH=25.660, Rm2_ohm=2.433,
        C0_pF=3.007, R0_ohm=30000.0, Rs_ohm=0.011,
        residual_norm=3.8919e-3, source="supplied_6p22_MBVD_schematic",
    ),
    "HIGH_7p40": MBVD(
        name="HIGH_7p40",
        Cm1_fF=200.000, Lm1_nH=2.314, Rm1_ohm=0.049,
        Cm2_fF=27.951, Lm2_nH=16.458, Rm2_ohm=0.584,
        C0_pF=3.572, R0_ohm=30000.0, Rs_ohm=0.010,
        residual_norm=8.2806e-4, source="supplied_7p40_MBVD_schematic",
    ),
    "SFR_7p49": MBVD(
        name="SFR_7p49",
        Cm1_fF=164.635, Lm1_nH=2.741, Rm1_ohm=0.065,
        Cm2_fF=55.983, Lm2_nH=8.040, Rm2_ohm=0.434,
        C0_pF=3.317, R0_ohm=30000.0, Rs_ohm=0.010,
        residual_norm=4.0373e-3, source="supplied_7p49_MBVD_schematic",
    ),
}


def load_comsol_data(path: str | Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load a COMSOL export containing frequency_GHz and log10(abs(I))."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    # sep=None handles tabs or whitespace in most COMSOL text exports.
    df = pd.read_csv(
        path, sep=None, engine="python", skiprows=1, header=None,
        comment="#"
    )
    if df.shape[1] < 2:
        # Fallback for irregular whitespace.
        df = pd.read_csv(
            path, sep=r"\s+", engine="python", skiprows=1, header=None,
            comment="#"
        )
    if df.shape[1] < 2:
        raise ValueError(f"{path}: expected at least two numeric columns")

    xy = df.iloc[:, :2].apply(pd.to_numeric, errors="coerce").dropna()
    if xy.empty:
        raise ValueError(f"{path}: no valid numeric rows")

    f_hz = xy.iloc[:, 0].to_numpy(float) * 1e9
    log_i = xy.iloc[:, 1].to_numpy(float)
    order = np.argsort(f_hz)
    return f_hz[order], log_i[order]


def mbvd_log_current(x: np.ndarray, f_hz: np.ndarray, vsrc: float = 5.0) -> np.ndarray:
    p = MBVD.from_fit_array("fit", x, float("nan"), "fit")
    z = p.z(f_hz)
    cur = vsrc / np.maximum(np.abs(z), np.finfo(float).tiny)
    return np.log10(cur)


def fit_mbvd_from_comsol(
    path: str | Path,
    seed: MBVD,
    vsrc: float = 5.0,
    verbose: bool = False,
) -> Tuple[MBVD, pd.DataFrame]:
    """
    Fit the double-motional MBVD structure shown in the supplied ADS schematics:
    two series Rm-Lm-Cm motional branches plus a series R0-C0 static-loss branch.

    The supplied schematic value is used as the initial point, which is much more
    stable than a generic starting point for these three resonator families.
    """
    f_hz, log_i = load_comsol_data(path)
    x0 = seed.as_fit_array()

    lb = np.array([
        1e-3, 1e-3, 1e-4,
        1e-3, 1e-3, 1e-4,
        1e-3, 1e3, 1e-4
    ], float)
    ub = np.array([
        500.0, 100.0, 100.0,
        500.0, 100.0, 100.0,
        50.0, 1e6, 100.0
    ], float)
    x0 = np.clip(x0, lb*(1+1e-9), ub*(1-1e-9))

    def residual(x):
        return mbvd_log_current(x, f_hz, vsrc) - log_i

    res = least_squares(
        residual, x0=x0, bounds=(lb, ub),
        method="trf", x_scale="jac",
        ftol=1e-10, xtol=1e-10, gtol=1e-10,
        max_nfev=10000,
        verbose=2 if verbose else 0,
    )
    norm = float(np.dot(res.fun, res.fun))
    fitted = MBVD.from_fit_array(
        seed.name, res.x, norm, f"COMSOL_fit:{Path(path).name}"
    )

    curve = pd.DataFrame({
        "Frequency_GHz": f_hz/1e9,
        "log10_absI_COMSOL": log_i,
        "log10_absI_MBVD": mbvd_log_current(res.x, f_hz, vsrc),
    })
    curve["residual"] = curve["log10_absI_MBVD"] - curve["log10_absI_COMSOL"]
    return fitted, curve


# =============================================================================
# 2. DFR 3Rx4 TOPOLOGY
# =============================================================================

@dataclass(frozen=True)
class Design:
    L3_nH: float = BASELINE["L3_nH"]
    L4_nH: float = BASELINE["L4_nH"]
    L5_nH: float = BASELINE["L5_nH"]
    L6_nH: float = BASELINE["L6_nH"]
    L7a_nH: float = BASELINE["L7_total_nH"]/3
    L7b_nH: float = BASELINE["L7_total_nH"]/3
    L7c_nH: float = BASELINE["L7_total_nH"]/3
    C1_pF: float = BASELINE["C1_pF"]

    @property
    def L7_total_nH(self) -> float:
        return self.L7a_nH + self.L7b_nH + self.L7c_nH

    def vector6(self) -> np.ndarray:
        return np.array([
            self.L3_nH, self.L4_nH, self.L5_nH,
            self.L6_nH, self.L7_total_nH, self.C1_pF
        ], float)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["L7_total_nH"] = self.L7_total_nH
        return d


def design_from_total(
    L3_nH: float,
    L4_nH: float,
    L5_nH: float,
    L6_nH: float,
    L7_total_nH: float,
    C1_pF: float,
    fractions: Sequence[float] = (1/3, 1/3, 1/3),
) -> Design:
    fr = np.asarray(fractions, float)
    fr = np.maximum(fr, 0.05)
    fr = fr / fr.sum()
    return Design(
        L3_nH=float(L3_nH),
        L4_nH=float(L4_nH),
        L5_nH=float(L5_nH),
        L6_nH=float(L6_nH),
        L7a_nH=float(L7_total_nH*fr[0]),
        L7b_nH=float(L7_total_nH*fr[1]),
        L7c_nH=float(L7_total_nH*fr[2]),
        C1_pF=float(C1_pF),
    )


def _identity_abcd(n: int) -> np.ndarray:
    m = np.zeros((n, 2, 2), complex)
    m[:, 0, 0] = 1
    m[:, 1, 1] = 1
    return m


def _series_abcd(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, complex)
    m = _identity_abcd(len(z))
    m[:, 0, 1] = z
    return m


def _shunt_abcd(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, complex)
    m = _identity_abcd(len(y))
    m[:, 1, 0] = y
    return m


def _cascade(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.einsum("nij,njk->nik", a, b)


def z_inductor(f_hz: np.ndarray, L_nH: float, qind: Optional[float]) -> np.ndarray:
    """
    Ideal/finite-Q inductor without parasitic Cp.
    Kept for nominal scenarios and for backwards-compatible internal use.
    """
    f = np.asarray(f_hz, float)
    L = L_nH * 1e-9
    r = 0.0 if qind is None else (2*np.pi*FREF_HZ*L/qind)
    return r + 1j*2*np.pi*f*L


def z_inductor_ads_exact(
    f_hz: np.ndarray,
    L_nH: float,
    qind: Optional[float],
    cp_fF: float,
) -> np.ndarray:
    """
    ADS-exact external inductor model used in the Qind/Cp scenarios:

        Z = R_fixed + ( j*w*L || 1/(j*w*Cp) )

    where:
        R_fixed = 2*pi*FREF_HZ*L/Qind

    Cp is the SAME value for every external inductor:
        L3, L4, L5, L6, L7a, L7b, L7c

    If cp_fF <= 0, this reduces to R_fixed + j*w*L.
    """
    f = np.asarray(f_hz, float)
    w = 2*np.pi*f
    L = L_nH * 1e-9

    r = 0.0 if qind is None else (2*np.pi*FREF_HZ*L/qind)
    zL = 1j*w*L

    if cp_fF <= 0:
        return r + zL

    Cp = cp_fF * 1e-15
    zC = 1/(1j*w*Cp)
    z_parallel = 1/(1/zL + 1/zC)

    return r + z_parallel


def z_capacitor(f_hz: np.ndarray, C_pF: float) -> np.ndarray:
    return 1/(1j*2*np.pi*np.asarray(f_hz, float)*C_pF*1e-12)


def y_cp(f_hz: np.ndarray, Cp_fF: float) -> np.ndarray:
    return 1j*2*np.pi*np.asarray(f_hz, float)*Cp_fF*1e-15


def simulate_dfr_3rxn(
    f_hz: np.ndarray,
    design: Design,
    low: MBVD,
    high: MBVD,
    n_cells: int = 4,
    qind: Optional[float] = DEFAULT_QIND,
    cp_total_fF: float = DEFAULT_CP_FF,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Circuit-level interpretation of the supplied cascaded DFR schematic.

    Each 3R cell:
        series L3
        [first cell only: shunt L4]
        series HIGH resonator
        shunt LOW resonator || HIGH resonator
        series L5
        series C1
        segmented series L7a/L7b/L7c

    In the final cell only, shunt L6 is placed after C1 and before segmented L7.

    ADS-exact Cp implementation:
        every external inductor (L3/L4/L5/L6/L7a/L7b/L7c) uses the SAME Cp value.
        Each inductor is modeled as:
            R_fixed + (L || Cp)
        where R_fixed = 2*pi*FREF_HZ*L/Qind.
        Cp is NOT divided by three.
    """
    f = np.asarray(f_hz, float)
    n = len(f)
    M = _identity_abcd(n)

    z_high = high.z(f)
    y_low_high = 1/low.z(f) + 1/high.z(f)

    for cell in range(n_cells):
        M = _cascade(M, _series_abcd(z_inductor_ads_exact(f, design.L3_nH, qind, cp_total_fF)))

        if cell == 0:
            M = _cascade(M, _shunt_abcd(1/z_inductor_ads_exact(f, design.L4_nH, qind, cp_total_fF)))

        M = _cascade(M, _series_abcd(z_high))
        M = _cascade(M, _shunt_abcd(y_low_high))

        M = _cascade(M, _series_abcd(z_inductor_ads_exact(f, design.L5_nH, qind, cp_total_fF)))
        M = _cascade(M, _series_abcd(z_capacitor(f, design.C1_pF)))

        # ADS-CONFIRMED L6 PLACEMENT:
        # L6 exists only in the FINAL cell. It is a shunt inductor connected
        # at the node AFTER C1 and BEFORE the segmented series L7 path.
        if cell == n_cells - 1:
            M = _cascade(
                M,
                _shunt_abcd(
                    1/z_inductor_ads_exact(f, design.L6_nH, qind, cp_total_fF)
                )
            )

        # ADS-exact segmented L7 implementation:
        # every segment uses the SAME Cp value, not Cp/3.
        # Each section is: R_fixed + (L || Cp).
        for seg in (design.L7a_nH, design.L7b_nH, design.L7c_nH):
            zseg = z_inductor_ads_exact(
                f,
                seg,
                qind,
                cp_total_fF,
            )
            M = _cascade(M, _series_abcd(zseg))

    A, B, C, D = M[:,0,0], M[:,0,1], M[:,1,0], M[:,1,1]
    den = A + B/Z0 + C*Z0 + D
    s21 = 2/den
    s11 = (A + B/Z0 - C*Z0 - D)/den
    return s11, s21


# =============================================================================
# 3. PYTHON VERIFICATION METRICS
# =============================================================================

def db20(x: np.ndarray) -> np.ndarray:
    return 20*np.log10(np.maximum(np.abs(x), 1e-15))


def _window(f_ghz: np.ndarray, lim: Tuple[float, float]) -> np.ndarray:
    return (f_ghz >= lim[0]) & (f_ghz <= lim[1])


def _tz(f_ghz: np.ndarray, s21_db: np.ndarray, lim: Tuple[float, float]) -> dict:
    m = _window(f_ghz, lim)
    if not np.any(m):
        return {"GHz": float("nan"), "S21_dB": float("nan")}
    ids = np.flatnonzero(m)
    k = ids[np.argmin(s21_db[m])]
    return {"GHz": float(f_ghz[k]), "S21_dB": float(s21_db[k])}


def _connected_3db_bw(
    f_ghz: np.ndarray, s21_db: np.ndarray, pb_mask: np.ndarray
) -> Tuple[float, float, float]:
    ids = np.flatnonzero(pb_mask)
    if len(ids) == 0:
        return float("nan"), float("nan"), float("nan")

    kpeak = ids[np.argmax(s21_db[pb_mask])]
    thr = s21_db[kpeak] - 3.0
    good = s21_db >= thr

    lo = kpeak
    hi = kpeak
    while lo > 0 and good[lo-1]:
        lo -= 1
    while hi < len(good)-1 and good[hi+1]:
        hi += 1
    return float(f_ghz[lo]), float(f_ghz[hi]), float(f_ghz[hi]-f_ghz[lo])


def metrics(
    f_ghz: np.ndarray,
    s11: np.ndarray,
    s21: np.ndarray,
) -> dict:
    s11d = db20(s11)
    s21d = db20(s21)

    pb = _window(f_ghz, PASSBAND_GHZ)
    lo = _window(f_ghz, LOW_STOP_GHZ)
    hi = _window(f_ghz, HIGH_STOP_GHZ)
    lo_near = _window(f_ghz, LOW_NEAR_STOP_GHZ)
    hi_near = _window(f_ghz, HIGH_NEAR_STOP_GHZ)

    if not np.any(pb):
        raise ValueError("frequency sweep does not cover the passband")

    f3lo, f3hi, bw = _connected_3db_bw(f_ghz, s21d, pb)
    peak = float(np.max(s21d[pb]))

    return {
        "minimum_IL_dB": float(-peak),
        "worst_passband_IL_dB": float(-np.min(s21d[pb])),
        "passband_ripple_dB": float(np.max(s21d[pb])-np.min(s21d[pb])),
        "worst_S11_dB": float(np.max(s11d[pb])),
        "S21_center_dB": float(np.interp(CENTER_GHZ, f_ghz, s21d)),
        "3dB_lower_GHz": f3lo,
        "3dB_upper_GHz": f3hi,
        "BW_3dB_GHz": bw,
        "lower_stopband_min_rejection_dB":
            float(-np.max(s21d[lo])) if np.any(lo) else float("nan"),
        "upper_stopband_min_rejection_dB":
            float(-np.max(s21d[hi])) if np.any(hi) else float("nan"),
        # Diagnostic only: broad windows include transition skirts and therefore
        # must NOT be reported as far-stopband rejection.
        "lower_near_stop_min_rejection_dB":
            float(-np.max(s21d[lo_near])) if np.any(lo_near) else float("nan"),
        "upper_near_stop_min_rejection_dB":
            float(-np.max(s21d[hi_near])) if np.any(hi_near) else float("nan"),
        "TZL": _tz(f_ghz, s21d, (5.90, 6.40)),
        "TZU": _tz(f_ghz, s21d, (7.20, 7.70)),
    }


SCENARIOS = [
    {"name": "nominal", "Qind": None, "Cp_fF": 0.0},
    {"name": "Q60_Cp60", "Qind": 60.0, "Cp_fF": 60.0},
    {"name": "Q40_Cp60", "Qind": 40.0, "Cp_fF": 60.0},
    {"name": "Q80_Cp30", "Qind": 80.0, "Cp_fF": 30.0},
]


def verify_design(
    design: Design,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    scenarios: Sequence[dict] = SCENARIOS,
) -> dict:
    out = {}
    f_hz = f_ghz * 1e9
    for s in scenarios:
        s11, s21 = simulate_dfr_3rxn(
            f_hz, design, low, high, n_cells=4,
            qind=s["Qind"], cp_total_fF=s["Cp_fF"],
        )
        out[s["name"]] = metrics(f_ghz, s11, s21)
    return out


def design_distance(d: Design) -> float:
    b = np.array([
        BASELINE["L3_nH"], BASELINE["L4_nH"], BASELINE["L5_nH"],
        BASELINE["L6_nH"], BASELINE["L7_total_nH"], BASELINE["C1_pF"]
    ], float)
    return float(np.sqrt(np.mean(((d.vector6()-b)/b)**2)))


def objective_tuple(verified: dict, design: Design) -> Tuple[float, ...]:
    """Ripple-first objectives; all are minimized.

    The DFR resonators already pin TZs close to 6.22/7.40 GHz, so matching
    quality gets priority. Nominal ripple is first, followed by Q60/Cp60
    ripple and implementation loss. TZ and rejection are guardrail terms.
    """
    mn = verified["nominal"]
    mq = verified["Q60_Cp60"]
    tzerr = abs(mq["TZL"]["GHz"]-TZ_TARGETS_GHZ[0]) + abs(mq["TZU"]["GHz"]-TZ_TARGETS_GHZ[1])
    rejection = min(mq["lower_stopband_min_rejection_dB"], mq["upper_stopband_min_rejection_dB"])
    bw_pen = max(0.0, 0.70 - mq["BW_3dB_GHz"])
    s11_pen = max(0.0, mq["worst_S11_dB"] + 10.0)
    return (
        mn["passband_ripple_dB"],
        mq["passband_ripple_dB"],
        mq["minimum_IL_dB"],
        mq["worst_passband_IL_dB"],
        s11_pen,
        bw_pen,
        tzerr,
        -rejection,
        design_distance(design),
    )

def dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


# =============================================================================
# 4. PARETO OPTIMIZATION
# =============================================================================

def random_design(rng: np.random.Generator) -> Design:
    """Ripple-first exploration around ADS checkpoint.

    L3, L5, and L7_total are held at the ADS checkpoint.
    L7 is always split equally into three physical series segments.
    Only L4, L6, and C1 are explored in the broad search.
    """
    L4 = float(np.clip(BASELINE["L4_nH"] * (1 + rng.uniform(-0.12, 0.12)), *BOUNDS["L4_nH"]))
    L6 = float(np.clip(BASELINE["L6_nH"] * (1 + rng.uniform(-0.12, 0.12)), *BOUNDS["L6_nH"]))
    C1 = float(np.clip(BASELINE["C1_pF"] * (1 + rng.uniform(-0.10, 0.10)), *BOUNDS["C1_pF"]))
    return design_from_total(
        BASELINE["L3_nH"], L4, BASELINE["L5_nH"], L6,
        BASELINE["L7_total_nH"], C1, (1/3, 1/3, 1/3)
    )

def pareto_optimize(
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    samples: int,
    seed: int,
) -> Tuple[pd.DataFrame, List[dict], dict]:
    rng = np.random.default_rng(seed)
    candidates: List[Design] = [
        design_from_total(**{
            "L3_nH": BASELINE["L3_nH"],
            "L4_nH": BASELINE["L4_nH"],
            "L5_nH": BASELINE["L5_nH"],
            "L6_nH": BASELINE["L6_nH"],
            "L7_total_nH": BASELINE["L7_total_nH"],
            "C1_pF": BASELINE["C1_pF"],
        })
    ]
    candidates += [random_design(rng) for _ in range(max(0, samples-1))]

    rows = []
    records = []

    for i, d in enumerate(candidates):
        v = verify_design(d, low, high, f_ghz)
        obj = objective_tuple(v, d)
        q = v["Q60_Cp60"]

        rec = {
            "candidate": i,
            "design": d,
            "verified": v,
            "objectives": obj,
        }
        records.append(rec)

        rows.append({
            "candidate": i,
            **d.to_dict(),
            "distance_from_baseline": design_distance(d),
            "Q60_Cp60_IL_dB": q["minimum_IL_dB"],
            "Q60_Cp60_ripple_dB": q["passband_ripple_dB"],
            "Q60_Cp60_BW3dB_GHz": q["BW_3dB_GHz"],
            "Q60_Cp60_rej_low_dB": q["lower_stopband_min_rejection_dB"],
            "Q60_Cp60_rej_high_dB": q["upper_stopband_min_rejection_dB"],
            "Q60_Cp60_TZL_GHz": q["TZL"]["GHz"],
            "Q60_Cp60_TZU_GHz": q["TZU"]["GHz"],
            "tz_error_GHz": obj[6],
        })

    is_pareto = np.ones(len(records), dtype=bool)
    for i, ri in enumerate(records):
        if not is_pareto[i]:
            continue
        for j, rj in enumerate(records):
            if i != j and dominates(rj["objectives"], ri["objectives"]):
                is_pareto[i] = False
                break

    pareto = [r for r, k in zip(records, is_pareto) if k]

    # Deterministic compromise choice:
    # min-max normalize Pareto objectives, then weighted sum.
    O = np.array([r["objectives"] for r in pareto], float)
    omin = np.nanmin(O, axis=0)
    omax = np.nanmax(O, axis=0)
    scale = np.where(omax > omin, omax-omin, 1.0)
    On = (O-omin)/scale
    weights = np.array([3.0, 2.4, 1.1, 1.2, 1.0, 2.0, 0.35, 0.35, 0.25])
    scores = On @ weights

    for r, score in zip(pareto, scores):
        r["compromise_score"] = float(score)

    best = min(pareto, key=lambda r: r["compromise_score"])

    df = pd.DataFrame(rows)
    df["pareto"] = is_pareto
    return df, pareto, best


# =============================================================================
# 5. COHERE ADVISORY
# =============================================================================

def _extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("No JSON object found in Cohere response")
    return json.loads(m.group(0))


def cohere_advisory(
    selected: dict,
    pareto: List[dict],
    model: str,
) -> dict:
    """
    Cohere sees only Python-verified results.
    It proposes a local search direction, not a final accepted design.
    """
    key = os.getenv("COHERE_API_KEY")
    if not key:
        return {
            "status": "skipped",
            "reason": "COHERE_API_KEY not set",
            "focus_parameters": ["L4_nH", "L6_nH", "C1_pF"],
            "direction": {"L4_nH": 0, "L6_nH": 0, "C1_pF": 0},
            "window_percent": 3.0,
            "summary": "Deterministic Python fallback local refinement.",
        }

    try:
        import cohere
    except ImportError:
        return {
            "status": "skipped",
            "reason": "cohere package not installed",
            "focus_parameters": ["L4_nH", "L6_nH", "C1_pF"],
            "direction": {"L4_nH": 0, "L6_nH": 0, "C1_pF": 0},
            "window_percent": 3.0,
            "summary": "Deterministic Python fallback local refinement.",
        }

    def compact_record(r: dict) -> dict:
        q = r["verified"]["Q60_Cp60"]
        return {
            "parameters": r["design"].to_dict(),
            "Q60_Cp60": q,
            "objectives": list(r["objectives"]),
            "compromise_score": r.get("compromise_score"),
        }

    evidence = {
        "rule": "Only the numerical values in this JSON are Python-verified.",
        "band_GHz": list(PASSBAND_GHZ),
        "center_GHz": CENTER_GHZ,
        "TZ_targets_GHz": list(TZ_TARGETS_GHZ),
        "selected_verified": compact_record(selected),
        "other_pareto_verified": [
            compact_record(r)
            for r in sorted(pareto, key=lambda x: x.get("compromise_score", 999))[:8]
        ],
        "allowed_parameters": list(BOUNDS),
        "constraints": [
            "Do not invent S-parameters or performance.",
            "Do not claim a proposed point is better until Python re-verifies it.",
            "Recommend only a conservative local refinement.",
            "Use 1 to 3 focus parameters.",
            "direction must be -1, 0, or +1 for each focus parameter.",
            "window_percent must be between 1 and 5.",
            "Preserve L7 as three physical series segments; optimize total locally and let Python redistribute safely.",
        ],
        "required_JSON_shape": {
            "focus_parameters": ["L4_nH", "L6_nH"],
            "direction": {"L4_nH": 1, "L6_nH": -1},
            "window_percent": 3.0,
            "summary": "short physical rationale",
            "risk": "main tradeoff to watch",
        },
    }

    system = (
        "You are the advisory layer of a physics-constrained FBAW filter design loop. "
        "The LLM proposes local experiments only; Python is the numerical authority. "
        "Return one JSON object only."
    )
    user = json.dumps(evidence, indent=2)

    try:
        co = cohere.ClientV2(api_key=key)
        res = co.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        chunks = []
        for item in getattr(res.message, "content", []) or []:
            txt = getattr(item, "text", None)
            if txt:
                chunks.append(txt)
            elif isinstance(item, dict) and item.get("text"):
                chunks.append(item["text"])
        advice = _extract_json_object("\n".join(chunks))
        advice["status"] = "ok"
        advice["model"] = model
        return advice
    except Exception as exc:
        return {
            "status": "error_fallback",
            "reason": str(exc),
            "focus_parameters": ["L4_nH", "L6_nH", "C1_pF"],
            "direction": {"L4_nH": 0, "L6_nH": 0, "C1_pF": 0},
            "window_percent": 3.0,
            "summary": "Cohere call failed; deterministic Python fallback used.",
        }


# =============================================================================
# 6. LOCAL REFINEMENT + PYTHON RE-VERIFICATION
# =============================================================================

def sanitize_advice(advice: dict) -> Tuple[List[str], Dict[str, int], float]:
    allowed = set(BOUNDS)
    fp = [x for x in advice.get("focus_parameters", []) if x in allowed]
    fp = fp[:3]
    if not fp:
        fp = ["L4_nH", "L6_nH", "C1_pF"]

    rawdir = advice.get("direction", {}) or {}
    directions = {}
    for k in fp:
        try:
            v = int(np.sign(float(rawdir.get(k, 0))))
        except Exception:
            v = 0
        directions[k] = v

    try:
        window = float(advice.get("window_percent", 3.0))
    except Exception:
        window = 3.0
    window = float(np.clip(window, 1.0, 5.0))
    return fp, directions, window


def total_params(d: Design) -> Dict[str, float]:
    return {
        "L3_nH": d.L3_nH,
        "L4_nH": d.L4_nH,
        "L5_nH": d.L5_nH,
        "L6_nH": d.L6_nH,
        "L7_total_nH": d.L7_total_nH,
        "C1_pF": d.C1_pF,
    }


def local_refine(
    base_record: dict,
    advice: dict,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
) -> Tuple[pd.DataFrame, dict]:
    focus, directions, window = sanitize_advice(advice)
    base = total_params(base_record["design"])

    # Five points per parameter; with max 3 parameters => <=125 re-verifications.
    grids = []
    for k in focus:
        center = base[k]
        frac = window/100.0
        if directions[k] > 0:
            lo, hi = center*(1-0.25*frac), center*(1+frac)
        elif directions[k] < 0:
            lo, hi = center*(1-frac), center*(1+0.25*frac)
        else:
            lo, hi = center*(1-frac), center*(1+frac)
        lo = max(lo, BOUNDS[k][0])
        hi = min(hi, BOUNDS[k][1])
        grids.append(np.linspace(lo, hi, 5))

    rows = []
    recs = []
    import itertools

    for idx, vv in enumerate(itertools.product(*grids)):
        p = dict(base)
        p.update({k: float(v) for k, v in zip(focus, vv)})

        # Keep the base L7 segmentation fractions when total L7 changes.
        bd = base_record["design"]
        fr = np.array([1/3, 1/3, 1/3], float)

        d = design_from_total(
            p["L3_nH"], p["L4_nH"], p["L5_nH"],
            p["L6_nH"], p["L7_total_nH"], p["C1_pF"], fr
        )
        v = verify_design(d, low, high, f_ghz)
        obj = objective_tuple(v, d)
        q = v["Q60_Cp60"]
        rec = {"design": d, "verified": v, "objectives": obj}
        recs.append(rec)
        rows.append({
            "local_candidate": idx,
            **d.to_dict(),
            "Q60_Cp60_IL_dB": q["minimum_IL_dB"],
            "Q60_Cp60_ripple_dB": q["passband_ripple_dB"],
            "Q60_Cp60_BW3dB_GHz": q["BW_3dB_GHz"],
            "Q60_Cp60_rej_low_dB": q["lower_stopband_min_rejection_dB"],
            "Q60_Cp60_rej_high_dB": q["upper_stopband_min_rejection_dB"],
            "Q60_Cp60_TZL_GHz": q["TZL"]["GHz"],
            "Q60_Cp60_TZU_GHz": q["TZU"]["GHz"],
            "tz_error_GHz": obj[6],
        })

    # Combine original selected point, so refinement cannot make the accepted result worse.
    allr = [base_record] + recs
    O = np.array([r["objectives"] for r in allr], float)
    omin, omax = np.nanmin(O, axis=0), np.nanmax(O, axis=0)
    scale = np.where(omax > omin, omax-omin, 1)
    On = (O-omin)/scale
    weights = np.array([3.0, 2.4, 1.1, 1.2, 1.0, 2.0, 0.35, 0.35, 0.25])
    score = On @ weights
    k = int(np.argmin(score))
    final = allr[k]
    final["local_compromise_score"] = float(score[k])
    final["accepted_from"] = "pre_LLM_selected" if k == 0 else "LLM_guided_local_refinement"

    return pd.DataFrame(rows), final


# =============================================================================
# 6B. Q60/Cp60 ROBUSTNESS TRIM
# =============================================================================

def robustness_feasible(v: dict) -> bool:
    mn = v["nominal"]
    mq = v["Q60_Cp60"]
    tz_ok = (
        abs(mq["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= ROBUST_TZ_TOL_GHZ
        and abs(mq["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= ROBUST_TZ_TOL_GHZ
    )
    return (
        mn["passband_ripple_dB"] <= ROBUST_NOMINAL_RIPPLE_MAX_DB
        and mq["BW_3dB_GHz"] >= ROBUST_Q60_BW_MIN_GHZ
        and tz_ok
    )


def robustness_key(v: dict) -> tuple:
    """Lexicographic: Q60/Cp60 ripple first, then IL, then nominal ripple."""
    mn = v["nominal"]
    mq = v["Q60_Cp60"]
    return (
        mq["passband_ripple_dB"],
        mq["minimum_IL_dB"],
        mq["worst_passband_IL_dB"],
        mn["passband_ripple_dB"],
        -mq["BW_3dB_GHz"],
    )


def sequential_robustness_trim(start_design: Design, low: MBVD, high: MBVD, f_ghz: np.ndarray):
    """Deterministic Q60/Cp60 robustness trim.

    L3, L5 and total L7 are fixed. L7 is always split equally.
    A new candidate can be accepted only if:
      1) Q60/Cp60 ripple is lower,
      2) nominal ripple <= 0.75 dB,
      3) Q60/Cp60 BW >= 0.78 GHz, and
      4) both TZs remain within +/-20 MHz of 6.22/7.40 GHz.
    """
    current = design_from_total(
        start_design.L3_nH, start_design.L4_nH, start_design.L5_nH,
        start_design.L6_nH, start_design.L7_total_nH, start_design.C1_pF,
        (1/3, 1/3, 1/3)
    )
    current_v = verify_design(current, low, high, f_ghz)
    if not robustness_feasible(current_v):
        raise RuntimeError("Historical robustness checkpoint violates configured constraints")

    history = []
    stages = [
        ("L4", ["L4_nH"], 0.060, 25),
        ("L6", ["L6_nH"], 0.070, 25),
        ("C1", ["C1_pF"], 0.055, 25),
        ("L4_L6", ["L4_nH", "L6_nH"], 0.030, 11),
        ("L4_L6_C1", ["L4_nH", "L6_nH", "C1_pF"], 0.018, 7),
    ]

    import itertools
    for stage_name, pars, frac, npts in stages:
        basep = total_params(current)
        grids = []
        for k in pars:
            lo = max(BOUNDS[k][0], basep[k]*(1-frac))
            hi = min(BOUNDS[k][1], basep[k]*(1+frac))
            grids.append(np.linspace(lo, hi, npts))

        best_d, best_v = current, current_v
        best_key = robustness_key(current_v)
        old_qr = current_v["Q60_Cp60"]["passband_ripple_dB"]

        for vals in itertools.product(*grids):
            p = dict(basep)
            p.update({k: float(v) for k, v in zip(pars, vals)})
            d = design_from_total(
                ROBUST_START["L3_nH"], p["L4_nH"], ROBUST_START["L5_nH"],
                p["L6_nH"], ROBUST_START["L7_total_nH"], p["C1_pF"],
                (1/3, 1/3, 1/3)
            )
            v = verify_design(d, low, high, f_ghz)
            if not robustness_feasible(v):
                continue
            k = robustness_key(v)
            # Primary acceptance condition is a strict Q60/Cp60 ripple improvement.
            if v["Q60_Cp60"]["passband_ripple_dB"] < old_qr - 1e-12 and k < best_key:
                best_key, best_d, best_v = k, d, v

        accepted = best_d is not current
        old_v = current_v
        if accepted:
            current, current_v = best_d, best_v

        history.append({
            "stage": stage_name,
            "accepted": bool(accepted),
            "design": current.to_dict(),
            "Q60_Cp60_ripple_before": old_v["Q60_Cp60"]["passband_ripple_dB"],
            "Q60_Cp60_ripple_after": current_v["Q60_Cp60"]["passband_ripple_dB"],
            "Q60_Cp60_IL_after": current_v["Q60_Cp60"]["minimum_IL_dB"],
            "Q60_Cp60_BW_after": current_v["Q60_Cp60"]["BW_3dB_GHz"],
            "nominal_ripple_after": current_v["nominal"]["passband_ripple_dB"],
            "TZL_after_GHz": current_v["Q60_Cp60"]["TZL"]["GHz"],
            "TZU_after_GHz": current_v["Q60_Cp60"]["TZU"]["GHz"],
        })
        print(
            f"{stage_name}: {'ACCEPT' if accepted else 'REJECT'} | Q60/Cp60 ripple "
            f"{old_v['Q60_Cp60']['passband_ripple_dB']:.6f} -> "
            f"{current_v['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
            f"nom={current_v['nominal']['passband_ripple_dB']:.6f} dB | "
            f"BW={current_v['Q60_Cp60']['BW_3dB_GHz']:.6f} GHz"
        )

    return current, current_v, history



# =============================================================================
# 6C. FINAL BALANCED L4/L6/C1 TRIM
# =============================================================================

def balanced_feasible(v: dict) -> bool:
    mn = v["nominal"]
    mq = v["Q60_Cp60"]
    return (
        mn["passband_ripple_dB"] <= ROBUST_NOMINAL_RIPPLE_MAX_DB
        and mq["BW_3dB_GHz"] >= ROBUST_Q60_BW_MIN_GHZ
        and abs(mq["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= ROBUST_TZ_TOL_GHZ
        and abs(mq["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= ROBUST_TZ_TOL_GHZ
    )


def balanced_score(v: dict) -> float:
    """
    Final compromise score.
    Both Q60/Cp60 ripple and minimum IL are primary.
    Hard constraints are handled separately by balanced_feasible().
    """
    mn = v["nominal"]
    mq = v["Q60_Cp60"]

    # Soft target penalties make 1.00-dB ripple and 1.27-dB IL the preferred region,
    # without forcing either metric to improve at the expense of the other.
    ripple = mq["passband_ripple_dB"]
    il = mq["minimum_IL_dB"]
    ripple_excess = max(0.0, ripple - BALANCED_RIPPLE_TARGET_DB)
    il_excess = max(0.0, il - BALANCED_IL_TARGET_DB)

    return (
        1.00 * ripple
        + 1.20 * il
        + 3.00 * ripple_excess
        + 3.00 * il_excess
        + 0.20 * mn["passband_ripple_dB"]
        - 0.08 * mq["BW_3dB_GHz"]
    )


def final_balanced_trim(start_design: Design, low: MBVD, high: MBVD, f_ghz: np.ndarray):
    """
    Small deterministic joint search around the latest robustness-final checkpoint.

    Fixed:
        L3, L5, total L7, equal L7 segmentation.

    Search windows:
        L4 +/-2%
        L6 +/-3%
        C1 +/-2%

    Two-pass grid refinement is used:
        coarse: 7 x 7 x 7
        fine:   7 x 7 x 7 around the coarse winner

    Candidate must satisfy:
        nominal ripple <= 0.78 dB
        Q60/Cp60 BW >= 0.80 GHz
        TZs within +/-20 MHz of 6.22/7.40 GHz
    """
    import itertools

    start = design_from_total(
        start_design.L3_nH, start_design.L4_nH, start_design.L5_nH,
        start_design.L6_nH, start_design.L7_total_nH, start_design.C1_pF,
        (1/3, 1/3, 1/3)
    )
    start_v = verify_design(start, low, high, f_ghz)
    if not balanced_feasible(start_v):
        raise RuntimeError("Balanced-trim checkpoint violates configured hard constraints")

    fixed = {
        "L3_nH": start.L3_nH,
        "L5_nH": start.L5_nH,
        "L7_total_nH": start.L7_total_nH,
    }

    rows = []
    best_d, best_v = start, start_v
    best_score = balanced_score(start_v)

    def run_grid(center: Design, frac4: float, frac6: float, fracc: float, npts: int, pass_name: str):
        nonlocal best_d, best_v, best_score
        centers = {
            "L4_nH": center.L4_nH,
            "L6_nH": center.L6_nH,
            "C1_pF": center.C1_pF,
        }
        grids = {
            "L4_nH": np.linspace(
                max(BOUNDS["L4_nH"][0], centers["L4_nH"]*(1-frac4)),
                min(BOUNDS["L4_nH"][1], centers["L4_nH"]*(1+frac4)),
                npts,
            ),
            "L6_nH": np.linspace(
                max(BOUNDS["L6_nH"][0], centers["L6_nH"]*(1-frac6)),
                min(BOUNDS["L6_nH"][1], centers["L6_nH"]*(1+frac6)),
                npts,
            ),
            "C1_pF": np.linspace(
                max(BOUNDS["C1_pF"][0], centers["C1_pF"]*(1-fracc)),
                min(BOUNDS["C1_pF"][1], centers["C1_pF"]*(1+fracc)),
                npts,
            ),
        }

        for idx, (l4, l6, c1) in enumerate(itertools.product(
            grids["L4_nH"], grids["L6_nH"], grids["C1_pF"]
        )):
            d = design_from_total(
                fixed["L3_nH"], float(l4), fixed["L5_nH"],
                float(l6), fixed["L7_total_nH"], float(c1),
                (1/3, 1/3, 1/3)
            )
            v = verify_design(d, low, high, f_ghz)
            if not balanced_feasible(v):
                continue

            s = balanced_score(v)
            q = v["Q60_Cp60"]
            n = v["nominal"]
            rows.append({
                "pass": pass_name,
                "candidate": idx,
                **d.to_dict(),
                "score": s,
                "Q60_Cp60_ripple_dB": q["passband_ripple_dB"],
                "Q60_Cp60_IL_dB": q["minimum_IL_dB"],
                "Q60_Cp60_worst_IL_dB": q["worst_passband_IL_dB"],
                "Q60_Cp60_BW3dB_GHz": q["BW_3dB_GHz"],
                "nominal_ripple_dB": n["passband_ripple_dB"],
                "nominal_IL_dB": n["minimum_IL_dB"],
                "TZL_GHz": q["TZL"]["GHz"],
                "TZU_GHz": q["TZU"]["GHz"],
            })

            if s < best_score - 1e-12:
                best_score, best_d, best_v = s, d, v

    # Coarse joint search.
    run_grid(start, 0.020, 0.030, 0.020, 7, "coarse")
    coarse_best = best_d

    # Fine search around the coarse winner.
    run_grid(coarse_best, 0.006, 0.009, 0.006, 7, "fine")

    accepted = balanced_score(best_v) < balanced_score(start_v) - 1e-12
    return best_d, best_v, start_v, pd.DataFrame(rows), accepted



# =============================================================================
# 6D. 3Rx4 CELL-BY-CELL NOMINAL RIPPLE OPTIMIZATION
# =============================================================================

# Adopted ADS-good nominal checkpoint requested by the user.
CELLWISE_START = {
    "L3_nH": 0.269000,
    "L4_nH": 0.614817,
    "L5_nH": 0.180000,
    "L6_nH": 0.951689,
    "L7a_nH": 0.24683333333333335,
    "L7b_nH": 0.24683333333333335,
    "L7c_nH": 0.24683333333333335,
    "C1_pF": 0.776990,
}

CELLWISE_TARGET_RIPPLE_DB = 0.50
CELLWISE_MIN_NOMINAL_BW_GHZ = 0.80
CELLWISE_TZ_TOL_GHZ = 0.025

@dataclass(frozen=True)
class CellParams:
    L3_nH: float
    L5_nH: float
    C1_pF: float
    L7a_nH: float
    L7b_nH: float
    L7c_nH: float

    @property
    def L7_total_nH(self) -> float:
        return self.L7a_nH + self.L7b_nH + self.L7c_nH

    def to_dict(self) -> dict:
        d = asdict(self)
        d["L7_total_nH"] = self.L7_total_nH
        return d


@dataclass(frozen=True)
class CellwiseDesign:
    cells: Tuple[CellParams, CellParams, CellParams, CellParams]
    L4_nH: float
    L6_nH: float

    def to_dict(self) -> dict:
        return {
            "L4_nH": self.L4_nH,
            "L6_nH": self.L6_nH,
            "cells": {
                f"cell{i+1}": c.to_dict()
                for i, c in enumerate(self.cells)
            },
        }


def make_uniform_cellwise_start() -> CellwiseDesign:
    c = CellParams(
        L3_nH=CELLWISE_START["L3_nH"],
        L5_nH=CELLWISE_START["L5_nH"],
        C1_pF=CELLWISE_START["C1_pF"],
        L7a_nH=CELLWISE_START["L7a_nH"],
        L7b_nH=CELLWISE_START["L7b_nH"],
        L7c_nH=CELLWISE_START["L7c_nH"],
    )
    return CellwiseDesign(
        cells=(c, c, c, c),
        L4_nH=CELLWISE_START["L4_nH"],
        L6_nH=CELLWISE_START["L6_nH"],
    )


def replace_cell(d: CellwiseDesign, cell_index: int, c: CellParams) -> CellwiseDesign:
    cells = list(d.cells)
    cells[cell_index] = c
    return CellwiseDesign(cells=tuple(cells), L4_nH=d.L4_nH, L6_nH=d.L6_nH)


def simulate_dfr_3rx4_cellwise(
    f_hz: np.ndarray,
    design: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    qind: Optional[float] = None,
    cp_fF: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    True 3Rx4 cell-wise implementation.

    Cell-specific parameters:
        L3, L5, C1, L7a, L7b, L7c

    Fixed terminal matching:
        L4 appears only in Cell 1
        L6 appears only in Cell 4, after C1 and before L7

    Q/Cp rule is preserved for later verification:
        every physical inductor, including EACH L7 segment, receives the full Cp.
        Thus L7a, L7b, L7c each have Cp=60 fF in Q60/Cp60 verification.
    """
    f = np.asarray(f_hz, float)
    M = _identity_abcd(len(f))
    z_high = high.z(f)
    y_low_high = 1/low.z(f) + 1/high.z(f)

    for i, c in enumerate(design.cells):
        M = _cascade(M, _series_abcd(
            z_inductor_ads_exact(f, c.L3_nH, qind, cp_fF)
        ))

        if i == 0:
            M = _cascade(M, _shunt_abcd(
                1/z_inductor_ads_exact(f, design.L4_nH, qind, cp_fF)
            ))

        M = _cascade(M, _series_abcd(z_high))
        M = _cascade(M, _shunt_abcd(y_low_high))

        M = _cascade(M, _series_abcd(
            z_inductor_ads_exact(f, c.L5_nH, qind, cp_fF)
        ))
        M = _cascade(M, _series_abcd(z_capacitor(f, c.C1_pF)))

        if i == 3:
            M = _cascade(M, _shunt_abcd(
                1/z_inductor_ads_exact(f, design.L6_nH, qind, cp_fF)
            ))

        # IMPORTANT: each physical L7 segment gets the full Cp value.
        for seg in (c.L7a_nH, c.L7b_nH, c.L7c_nH):
            M = _cascade(M, _series_abcd(
                z_inductor_ads_exact(f, seg, qind, cp_fF)
            ))

    A, B, C, D = M[:,0,0], M[:,0,1], M[:,1,0], M[:,1,1]
    den = A + B/Z0 + C*Z0 + D
    s21 = 2/den
    s11 = (A + B/Z0 - C*Z0 - D)/den
    return s11, s21


def verify_cellwise(design: CellwiseDesign, low: MBVD, high: MBVD, f_ghz: np.ndarray) -> dict:
    out = {}
    for name, q, cp in (
        ("nominal", None, 0.0),
        ("Q60_Cp60", 60.0, 60.0),
    ):
        s11, s21 = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, design, low, high, qind=q, cp_fF=cp
        )
        out[name] = metrics(f_ghz, s11, s21)
    return out


# Conservative cell-local bounds around the adopted ADS-good checkpoint.
_CELLWISE_BOUNDS = {
    "L3_nH": (0.245, 0.295),
    "L5_nH": (0.160, 0.205),
    "C1_pF": (0.700, 0.850),
    "L7a_nH": (0.215, 0.280),
    "L7b_nH": (0.215, 0.280),
    "L7c_nH": (0.215, 0.280),
}


def _cell_vector(c: CellParams) -> np.ndarray:
    return np.array([
        c.L3_nH, c.L5_nH, c.C1_pF,
        c.L7a_nH, c.L7b_nH, c.L7c_nH
    ], float)


def _cell_from_vector(x: Sequence[float]) -> CellParams:
    return CellParams(
        L3_nH=float(x[0]),
        L5_nH=float(x[1]),
        C1_pF=float(x[2]),
        L7a_nH=float(x[3]),
        L7b_nH=float(x[4]),
        L7c_nH=float(x[5]),
    )


def _nominal_guard(m: dict) -> bool:
    return (
        m["BW_3dB_GHz"] >= CELLWISE_MIN_NOMINAL_BW_GHZ
        and abs(m["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= CELLWISE_TZ_TOL_GHZ
        and abs(m["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= CELLWISE_TZ_TOL_GHZ
    )


def optimize_one_cell_nominal(
    base: CellwiseDesign,
    cell_index: int,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
) -> Tuple[CellwiseDesign, dict, pd.DataFrame]:
    """
    Optimize ONE cell only; every other cell and L4/L6 are frozen.

    Stage A: deterministic coordinate sweep over the six cell parameters.
    Stage B: bounded Powell joint polish of those same six parameters.
    The result is accepted only when nominal ripple is lower and guardrails pass.
    """
    from scipy.optimize import minimize

    current = base
    vcur = verify_cellwise(current, low, high, f_ghz)
    best_ripple = vcur["nominal"]["passband_ripple_dB"]
    rows = []

    names = ["L3_nH", "L5_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"]

    # Coordinate descent: three passes, fine local sweeps.
    for sweep_pass in range(3):
        improved_this_pass = False
        for pidx, name in enumerate(names):
            c0 = current.cells[cell_index]
            x0 = _cell_vector(c0)
            center = x0[pidx]
            lo_abs, hi_abs = _CELLWISE_BOUNDS[name]
            frac = 0.060 if sweep_pass == 0 else (0.030 if sweep_pass == 1 else 0.015)
            vals = np.linspace(max(lo_abs, center*(1-frac)), min(hi_abs, center*(1+frac)), 17)

            local_best = current
            local_v = vcur
            local_r = best_ripple

            for val in vals:
                x = x0.copy()
                x[pidx] = val
                cand = replace_cell(current, cell_index, _cell_from_vector(x))
                vv = verify_cellwise(cand, low, high, f_ghz)
                mn = vv["nominal"]
                rows.append({
                    "cell": cell_index + 1,
                    "stage": f"coordinate_pass_{sweep_pass+1}",
                    "parameter": name,
                    "trial_value": float(val),
                    "nominal_ripple_dB": mn["passband_ripple_dB"],
                    "nominal_IL_dB": mn["minimum_IL_dB"],
                    "nominal_BW_GHz": mn["BW_3dB_GHz"],
                    "TZL_GHz": mn["TZL"]["GHz"],
                    "TZU_GHz": mn["TZU"]["GHz"],
                })
                if _nominal_guard(mn) and mn["passband_ripple_dB"] < local_r - 1e-7:
                    local_best, local_v = cand, vv
                    local_r = mn["passband_ripple_dB"]

            if local_r < best_ripple - 1e-7:
                current, vcur, best_ripple = local_best, local_v, local_r
                improved_this_pass = True

        if not improved_this_pass:
            break

    # Joint bounded polish for the same one cell.
    x_start = _cell_vector(current.cells[cell_index])
    bounds = [_CELLWISE_BOUNDS[n] for n in names]

    def objective(x):
        cand = replace_cell(current, cell_index, _cell_from_vector(x))
        s11, s21 = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, cand, low, high, qind=None, cp_fF=0.0
        )
        mn = metrics(f_ghz, s11, s21)
        ripple = mn["passband_ripple_dB"]
        penalty = 0.0
        if mn["BW_3dB_GHz"] < CELLWISE_MIN_NOMINAL_BW_GHZ:
            penalty += 100.0*(CELLWISE_MIN_NOMINAL_BW_GHZ-mn["BW_3dB_GHz"])**2
        penalty += 100.0*max(0.0, abs(mn["TZL"]["GHz"]-TZ_TARGETS_GHZ[0])-CELLWISE_TZ_TOL_GHZ)**2
        penalty += 100.0*max(0.0, abs(mn["TZU"]["GHz"]-TZ_TARGETS_GHZ[1])-CELLWISE_TZ_TOL_GHZ)**2
        return ripple + penalty

    res = minimize(
        objective, x_start, method="Powell", bounds=bounds,
        options={"maxiter": 220, "xtol": 1e-7, "ftol": 1e-9, "disp": False},
    )
    polish = replace_cell(current, cell_index, _cell_from_vector(res.x))
    vpol = verify_cellwise(polish, low, high, f_ghz)
    if _nominal_guard(vpol["nominal"]) and vpol["nominal"]["passband_ripple_dB"] < best_ripple - 1e-7:
        current, vcur = polish, vpol

    return current, vcur, pd.DataFrame(rows)


def cell_by_cell_nominal_optimize(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Step-by-step sequence requested by the user.

    1) Cell 2 only.
    2) Only if Cell 2 improves: Cell 3.
    3) Only if still useful: Cell 1.
    4) Then Cell 4.

    At every step all previously accepted values are frozen except the one cell
    currently being optimized. If a cell gives no improvement, it is rejected.
    Stop early if nominal ripple reaches 0.50 dB.
    """
    order = [1, 2, 0, 3]  # zero-based: Cell 2 -> 3 -> 1 -> 4
    current = start
    vcur = verify_cellwise(current, low, high, f_ghz)
    history = []
    all_rows = []

    start_r = vcur["nominal"]["passband_ripple_dB"]
    print(f"Start checkpoint: nominal ripple={start_r:.6f} dB")

    for idx in order:
        before = current
        vbefore = vcur
        r0 = vbefore["nominal"]["passband_ripple_dB"]

        trial, vtrial, rows = optimize_one_cell_nominal(
            current, idx, low, high, f_ghz
        )
        if not rows.empty:
            all_rows.append(rows)

        r1 = vtrial["nominal"]["passband_ripple_dB"]
        accept = r1 < r0 - 1e-6

        if accept:
            current, vcur = trial, vtrial
            print(f"Cell {idx+1}: ACCEPT | nominal ripple {r0:.6f} -> {r1:.6f} dB")
        else:
            current, vcur = before, vbefore
            r1 = r0
            print(f"Cell {idx+1}: REJECT | nominal ripple remains {r0:.6f} dB")

        history.append({
            "cell": idx+1,
            "accepted": bool(accept),
            "ripple_before_dB": r0,
            "ripple_after_dB": r1,
            "design_after": current.to_dict(),
        })

        if vcur["nominal"]["passband_ripple_dB"] <= CELLWISE_TARGET_RIPPLE_DB:
            print(f"TARGET REACHED: nominal ripple <= {CELLWISE_TARGET_RIPPLE_DB:.2f} dB")
            break

    search_df = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    return current, vcur, history, search_df



# =============================================================================
# 6E. NOMINAL FINE CYCLIC TRIM + S11/S21 PLOTS
# =============================================================================

FINE_TARGET_RIPPLE_DB = 0.50
FINE_MAX_PASSES = 3

# Fine windows relative to each current accepted cell value.
# Pass 1: +/-1.0%, Pass 2: +/-0.5%, Pass 3: +/-0.25%.
FINE_WINDOWS = (0.010, 0.005, 0.0025)

# Fine cyclic order: revisit Cell 1 AFTER Cell 4 has already changed the network,
# then continue through Cells 2, 3, 4.
FINE_CELL_ORDER = (0, 1, 2, 3)


def fine_optimize_one_cell_nominal(
    base: CellwiseDesign,
    cell_index: int,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    frac: float,
) -> Tuple[CellwiseDesign, dict]:
    """
    Very small coordinate search on one cell only.

    Parameters allowed to move:
        L3, L5, C1, L7a, L7b, L7c

    All other cells and L4/L6 remain fixed.
    Candidate is accepted only if nominal ripple improves and guardrails pass.
    """
    names = ["L3_nH", "L5_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"]

    current = base
    vcur = verify_cellwise(current, low, high, f_ghz)
    best_ripple = vcur["nominal"]["passband_ripple_dB"]

    # Two coordinate sweeps inside each fine cell step.
    for _ in range(2):
        improved = False
        for pidx, name in enumerate(names):
            c0 = current.cells[cell_index]
            x0 = _cell_vector(c0)
            center = x0[pidx]
            lo_abs, hi_abs = _CELLWISE_BOUNDS[name]

            lo = max(lo_abs, center*(1-frac))
            hi = min(hi_abs, center*(1+frac))
            vals = np.linspace(lo, hi, 13)

            local_best = current
            local_v = vcur
            local_r = best_ripple

            for val in vals:
                x = x0.copy()
                x[pidx] = float(val)
                cand = replace_cell(current, cell_index, _cell_from_vector(x))
                vv = verify_cellwise(cand, low, high, f_ghz)
                mn = vv["nominal"]

                if (
                    _nominal_guard(mn)
                    and mn["passband_ripple_dB"] < local_r - 1e-8
                ):
                    local_best = cand
                    local_v = vv
                    local_r = mn["passband_ripple_dB"]

            if local_r < best_ripple - 1e-8:
                current = local_best
                vcur = local_v
                best_ripple = local_r
                improved = True

        if not improved:
            break

    return current, vcur


def fine_cyclic_nominal_trim(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Revisit all 4 cells with shrinking fine windows.

    Pass 1: +/-1.00%
    Pass 2: +/-0.50%
    Pass 3: +/-0.25%

    Cell order each pass:
        Cell 1 -> Cell 2 -> Cell 3 -> Cell 4

    Only accept a cell change when nominal ripple decreases.
    Stop immediately if nominal ripple reaches <=0.50 dB.
    """
    current = start
    vcur = verify_cellwise(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("NOMINAL FINE CYCLIC TRIM")
    print("="*78)
    print(f"Fine-start ripple={vcur['nominal']['passband_ripple_dB']:.6f} dB")

    for pass_idx, frac in enumerate(FINE_WINDOWS, start=1):
        print(f"\nFine pass {pass_idx}: window +/-{100*frac:.3f}%")
        pass_improved = False

        for cell_index in FINE_CELL_ORDER:
            r0 = vcur["nominal"]["passband_ripple_dB"]

            trial, vtrial = fine_optimize_one_cell_nominal(
                current, cell_index, low, high, f_ghz, frac
            )
            r1 = vtrial["nominal"]["passband_ripple_dB"]
            accept = r1 < r0 - 1e-7

            if accept:
                current = trial
                vcur = vtrial
                pass_improved = True
                print(
                    f"Cell {cell_index+1}: ACCEPT | nominal ripple "
                    f"{r0:.6f} -> {r1:.6f} dB"
                )
            else:
                print(
                    f"Cell {cell_index+1}: REJECT | nominal ripple "
                    f"remains {r0:.6f} dB"
                )
                r1 = r0

            history.append({
                "pass": pass_idx,
                "window_percent": 100*frac,
                "cell": cell_index+1,
                "accepted": bool(accept),
                "ripple_before_dB": r0,
                "ripple_after_dB": r1,
                "design_after": current.to_dict(),
            })

            if vcur["nominal"]["passband_ripple_dB"] <= FINE_TARGET_RIPPLE_DB:
                print(
                    f"TARGET REACHED: nominal ripple <= "
                    f"{FINE_TARGET_RIPPLE_DB:.2f} dB"
                )
                return current, vcur, history

        if not pass_improved:
            print("No improvement in this fine pass; stopping.")
            break

    return current, vcur, history


def plot_cellwise_sparams(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    start: CellwiseDesign,
    final: CellwiseDesign,
) -> None:
    if plt is None:
        return

    # Nominal responses.
    s11_start, s21_start = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, start, low, high, qind=None, cp_fF=0.0
    )
    s11_final, s21_final = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=None, cp_fF=0.0
    )

    # S21 image.
    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_start), label="Start nominal")
    plt.plot(f_ghz, db20(s21_final), label="Final nominal")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-3.0, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Nominal S21 - Cell-by-Cell Fine Cyclic Trim")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"12_nominal_S21_start_vs_final.png", dpi=220)
    plt.close(fig)

    # S11 image.
    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s11_start), label="Start nominal")
    plt.plot(f_ghz, db20(s11_final), label="Final nominal")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-10.0, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("3Rx4 Nominal S11 - Cell-by-Cell Fine Cyclic Trim")
    plt.ylim(-40, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"13_nominal_S11_start_vs_final.png", dpi=220)
    plt.close(fig)

    # Combined Q60/Cp60 check image (not optimized, just diagnostic).
    s11_q, s21_q = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=60.0, cp_fF=60.0
    )
    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_q), label="S21 Q60/Cp60")
    plt.plot(f_ghz, db20(s11_q), label="S11 Q60/Cp60")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Magnitude (dB)")
    plt.title("3Rx4 Final Q60/Cp60 Diagnostic")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"14_Q60Cp60_S11_S21_diagnostic.png", dpi=220)
    plt.close(fig)



# =============================================================================
# 6F. FINAL TERMINAL MATCHING TRIM: L4 / L6 ONLY
# =============================================================================

TERMINAL_TARGET_RIPPLE_DB = 0.50
TERMINAL_MIN_NOMINAL_BW_GHZ = 0.80
TERMINAL_TZ_TOL_GHZ = 0.025
TERMINAL_MIN_ACCEPT_IMPROVEMENT_DB = 1e-6


def replace_terminals(d: CellwiseDesign, L4_nH=None, L6_nH=None) -> CellwiseDesign:
    return CellwiseDesign(
        cells=d.cells,
        L4_nH=d.L4_nH if L4_nH is None else float(L4_nH),
        L6_nH=d.L6_nH if L6_nH is None else float(L6_nH),
    )


def terminal_guard(v: dict) -> bool:
    mn = v["nominal"]
    return (
        mn["BW_3dB_GHz"] >= TERMINAL_MIN_NOMINAL_BW_GHZ
        and abs(mn["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= TERMINAL_TZ_TOL_GHZ
        and abs(mn["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= TERMINAL_TZ_TOL_GHZ
    )


def terminal_score(v: dict) -> float:
    """
    Nominal ripple remains the dominant objective.
    A very light S11 term is used only to break near-ties.
    """
    mn = v["nominal"]
    # worst_S11_dB is negative; more negative is better.
    return (
        mn["passband_ripple_dB"]
        + 0.01 * max(0.0, mn["worst_S11_dB"] + 10.0)
    )


def optimize_terminal_1d(
    base: CellwiseDesign,
    which: str,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    v0 = verify_cellwise(base, low, high, f_ghz)
    best_d, best_v = base, v0
    best_score = terminal_score(v0)

    center = base.L4_nH if which == "L4" else base.L6_nH
    vals = np.linspace(center*(1-frac), center*(1+frac), 41)

    for val in vals:
        cand = replace_terminals(
            base,
            L4_nH=val if which == "L4" else None,
            L6_nH=val if which == "L6" else None,
        )
        vv = verify_cellwise(cand, low, high, f_ghz)
        if not terminal_guard(vv):
            continue
        s = terminal_score(vv)
        if s < best_score - 1e-12:
            best_d, best_v, best_score = cand, vv, s

    return best_d, best_v


def optimize_terminal_2d(
    base: CellwiseDesign,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    v0 = verify_cellwise(base, low, high, f_ghz)
    best_d, best_v = base, v0
    best_score = terminal_score(v0)

    l4vals = np.linspace(base.L4_nH*(1-frac), base.L4_nH*(1+frac), 31)
    l6vals = np.linspace(base.L6_nH*(1-frac), base.L6_nH*(1+frac), 31)

    for l4 in l4vals:
        for l6 in l6vals:
            cand = replace_terminals(base, L4_nH=l4, L6_nH=l6)
            vv = verify_cellwise(cand, low, high, f_ghz)
            if not terminal_guard(vv):
                continue
            s = terminal_score(vv)
            if s < best_score - 1e-12:
                best_d, best_v, best_score = cand, vv, s

    return best_d, best_v


def final_terminal_trim(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Freeze every per-cell parameter and trim only terminal L4/L6.

    Stage 1, coarse:
        L4 only +/-1%
        L6 only +/-1%
        L4+L6 coordinated +/-1%

    Stage 2, fine:
        repeat with +/-0.3%

    A stage is accepted only if nominal ripple improves by >1e-6 dB.
    """
    current = start
    vcur = verify_cellwise(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("FINAL TERMINAL L4/L6 MATCHING TRIM")
    print("="*78)
    print(
        f"Terminal-start ripple={vcur['nominal']['passband_ripple_dB']:.6f} dB | "
        f"L4={current.L4_nH:.9f} nH, L6={current.L6_nH:.9f} nH"
    )

    for pass_name, frac in (("coarse", 0.010), ("fine", 0.003)):
        print(f"\n{pass_name.upper()} terminal pass: +/-{100*frac:.3f}%")

        for stage in ("L4", "L6", "L4_L6"):
            r0 = vcur["nominal"]["passband_ripple_dB"]
            before = current

            if stage == "L4":
                trial, vtrial = optimize_terminal_1d(
                    current, "L4", frac, low, high, f_ghz
                )
            elif stage == "L6":
                trial, vtrial = optimize_terminal_1d(
                    current, "L6", frac, low, high, f_ghz
                )
            else:
                trial, vtrial = optimize_terminal_2d(
                    current, frac, low, high, f_ghz
                )

            r1 = vtrial["nominal"]["passband_ripple_dB"]
            improvement = r0 - r1
            accept = (
                terminal_guard(vtrial)
                and improvement > TERMINAL_MIN_ACCEPT_IMPROVEMENT_DB
            )

            if accept:
                current, vcur = trial, vtrial
                print(
                    f"{stage}: ACCEPT | nominal ripple "
                    f"{r0:.6f} -> {r1:.6f} dB | "
                    f"L4={current.L4_nH:.9f}, L6={current.L6_nH:.9f}"
                )
            else:
                current = before
                print(
                    f"{stage}: REJECT | nominal ripple remains "
                    f"{r0:.6f} dB"
                )
                r1 = r0

            history.append({
                "pass": pass_name,
                "window_percent": 100*frac,
                "stage": stage,
                "accepted": bool(accept),
                "ripple_before_dB": r0,
                "ripple_after_dB": r1,
                "L4_nH": current.L4_nH,
                "L6_nH": current.L6_nH,
            })

            if vcur["nominal"]["passband_ripple_dB"] <= TERMINAL_TARGET_RIPPLE_DB:
                print(
                    f"TARGET REACHED: nominal ripple <= "
                    f"{TERMINAL_TARGET_RIPPLE_DB:.2f} dB"
                )
                return current, vcur, history

    return current, vcur, history


def plot_terminal_sparams(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    pre_terminal: CellwiseDesign,
    final: CellwiseDesign,
) -> None:
    if plt is None:
        return

    s11_pre, s21_pre = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, pre_terminal, low, high, qind=None, cp_fF=0.0
    )
    s11_fin, s21_fin = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=None, cp_fF=0.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_pre), label="Before terminal trim")
    plt.plot(f_ghz, db20(s21_fin), label="After terminal trim")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Nominal S21 - Final L4/L6 Terminal Trim")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"15_terminal_trim_nominal_S21.png", dpi=220)
    plt.close(fig)

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s11_pre), label="Before terminal trim")
    plt.plot(f_ghz, db20(s11_fin), label="After terminal trim")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-10.0, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("3Rx4 Nominal S11 - Final L4/L6 Terminal Trim")
    plt.ylim(-40, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"16_terminal_trim_nominal_S11.png", dpi=220)
    plt.close(fig)

    s11_q, s21_q = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=60.0, cp_fF=60.0
    )
    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_q), label="S21 Q60/Cp60")
    plt.plot(f_ghz, db20(s11_q), label="S11 Q60/Cp60")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Magnitude (dB)")
    plt.title("3Rx4 Final Q60/Cp60 Diagnostic After Terminal Trim")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"17_terminal_trim_Q60Cp60_diagnostic.png", dpi=220)
    plt.close(fig)



# =============================================================================
# 6G. FINAL L6-DIRECTED TERMINAL EXTENSION
# =============================================================================

L6_EXT_TARGET_RIPPLE_DB = 0.50
L6_EXT_MIN_BW_GHZ = 0.80
L6_EXT_TZ_TOL_GHZ = 0.025
L6_EXT_WORST_S11_MIN_DB = -8.5
L6_EXT_MIN_ACCEPT_IMPROVEMENT_DB = 1e-6


def l6ext_guard(v: dict) -> bool:
    mn = v["nominal"]
    return (
        mn["BW_3dB_GHz"] >= L6_EXT_MIN_BW_GHZ
        and abs(mn["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= L6_EXT_TZ_TOL_GHZ
        and abs(mn["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= L6_EXT_TZ_TOL_GHZ
        and mn["worst_S11_dB"] <= L6_EXT_WORST_S11_MIN_DB
    )


def l6_directed_extension(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Freeze all 4 cells completely.

    Stage 1:
        L6 only, directed upward from 0% to +2.0%

    Stage 2:
        L4 only, +/-0.4% around Stage-1 winner

    Stage 3:
        L4 +/-0.3%, L6 +/-0.5% coordinated fine search

    Stop early if nominal ripple <= 0.50 dB.
    """
    current = start
    vcur = verify_cellwise(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("FINAL L6-DIRECTED TERMINAL EXTENSION")
    print("="*78)
    print(
        f"Start ripple={vcur['nominal']['passband_ripple_dB']:.6f} dB | "
        f"L4={current.L4_nH:.9f} nH, L6={current.L6_nH:.9f} nH | "
        f"S11worst={vcur['nominal']['worst_S11_dB']:.3f} dB"
    )

    # -------------------------------------------------------------------------
    # Stage 1: L6 ONLY, one-way upward search 0 -> +2.0%.
    # -------------------------------------------------------------------------
    r0 = vcur["nominal"]["passband_ripple_dB"]
    best_d, best_v = current, vcur
    best_r = r0

    l6_values = np.linspace(current.L6_nH, current.L6_nH * 1.020, 81)

    for l6 in l6_values:
        cand = replace_terminals(current, L6_nH=float(l6))
        vv = verify_cellwise(cand, low, high, f_ghz)
        if not l6ext_guard(vv):
            continue
        rr = vv["nominal"]["passband_ripple_dB"]
        if rr < best_r - 1e-12:
            best_d, best_v, best_r = cand, vv, rr

    improvement = r0 - best_r
    accept = improvement > L6_EXT_MIN_ACCEPT_IMPROVEMENT_DB
    if accept:
        current, vcur = best_d, best_v
        print(
            f"L6_DIRECTED: ACCEPT | nominal ripple {r0:.6f} -> {best_r:.6f} dB | "
            f"L6={current.L6_nH:.9f} nH"
        )
    else:
        print(
            f"L6_DIRECTED: REJECT | nominal ripple remains {r0:.6f} dB"
        )

    history.append({
        "stage": "L6_directed_0_to_plus2pct",
        "accepted": bool(accept),
        "ripple_before_dB": r0,
        "ripple_after_dB": vcur["nominal"]["passband_ripple_dB"],
        "L4_nH": current.L4_nH,
        "L6_nH": current.L6_nH,
    })

    if vcur["nominal"]["passband_ripple_dB"] <= L6_EXT_TARGET_RIPPLE_DB:
        print(f"TARGET REACHED after L6-directed stage: <= {L6_EXT_TARGET_RIPPLE_DB:.2f} dB")
        return current, vcur, history

    # -------------------------------------------------------------------------
    # Stage 2: L4 ONLY, +/-0.4%.
    # -------------------------------------------------------------------------
    r0 = vcur["nominal"]["passband_ripple_dB"]
    best_d, best_v = current, vcur
    best_r = r0

    l4_values = np.linspace(current.L4_nH * 0.996, current.L4_nH * 1.004, 61)

    for l4 in l4_values:
        cand = replace_terminals(current, L4_nH=float(l4))
        vv = verify_cellwise(cand, low, high, f_ghz)
        if not l6ext_guard(vv):
            continue
        rr = vv["nominal"]["passband_ripple_dB"]
        if rr < best_r - 1e-12:
            best_d, best_v, best_r = cand, vv, rr

    improvement = r0 - best_r
    accept = improvement > L6_EXT_MIN_ACCEPT_IMPROVEMENT_DB
    if accept:
        current, vcur = best_d, best_v
        print(
            f"L4_COMP: ACCEPT | nominal ripple {r0:.6f} -> {best_r:.6f} dB | "
            f"L4={current.L4_nH:.9f} nH"
        )
    else:
        print(
            f"L4_COMP: REJECT | nominal ripple remains {r0:.6f} dB"
        )

    history.append({
        "stage": "L4_comp_plusminus0p4pct",
        "accepted": bool(accept),
        "ripple_before_dB": r0,
        "ripple_after_dB": vcur["nominal"]["passband_ripple_dB"],
        "L4_nH": current.L4_nH,
        "L6_nH": current.L6_nH,
    })

    if vcur["nominal"]["passband_ripple_dB"] <= L6_EXT_TARGET_RIPPLE_DB:
        print(f"TARGET REACHED after L4 compensation: <= {L6_EXT_TARGET_RIPPLE_DB:.2f} dB")
        return current, vcur, history

    # -------------------------------------------------------------------------
    # Stage 3: L4 +/-0.3%, L6 +/-0.5% coordinated fine search.
    # -------------------------------------------------------------------------
    r0 = vcur["nominal"]["passband_ripple_dB"]
    best_d, best_v = current, vcur
    best_r = r0

    l4_values = np.linspace(current.L4_nH * 0.997, current.L4_nH * 1.003, 41)
    l6_values = np.linspace(current.L6_nH * 0.995, current.L6_nH * 1.005, 61)

    for l4 in l4_values:
        for l6 in l6_values:
            cand = replace_terminals(current, L4_nH=float(l4), L6_nH=float(l6))
            vv = verify_cellwise(cand, low, high, f_ghz)
            if not l6ext_guard(vv):
                continue
            rr = vv["nominal"]["passband_ripple_dB"]
            if rr < best_r - 1e-12:
                best_d, best_v, best_r = cand, vv, rr

    improvement = r0 - best_r
    accept = improvement > L6_EXT_MIN_ACCEPT_IMPROVEMENT_DB
    if accept:
        current, vcur = best_d, best_v
        print(
            f"L4_L6_FINE: ACCEPT | nominal ripple {r0:.6f} -> {best_r:.6f} dB | "
            f"L4={current.L4_nH:.9f}, L6={current.L6_nH:.9f}"
        )
    else:
        print(
            f"L4_L6_FINE: REJECT | nominal ripple remains {r0:.6f} dB"
        )

    history.append({
        "stage": "L4_L6_joint_fine",
        "accepted": bool(accept),
        "ripple_before_dB": r0,
        "ripple_after_dB": vcur["nominal"]["passband_ripple_dB"],
        "L4_nH": current.L4_nH,
        "L6_nH": current.L6_nH,
    })

    return current, vcur, history


def plot_l6_extension_sparams(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    pre_extension: CellwiseDesign,
    final: CellwiseDesign,
) -> None:
    if plt is None:
        return

    s11_pre, s21_pre = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, pre_extension, low, high, qind=None, cp_fF=0.0
    )
    s11_fin, s21_fin = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=None, cp_fF=0.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_pre), label="Before L6-directed extension")
    plt.plot(f_ghz, db20(s21_fin), label="After L6-directed extension")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Nominal S21 - Final L6-Directed Extension")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"19_L6_directed_nominal_S21.png", dpi=220)
    plt.close(fig)

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s11_pre), label="Before L6-directed extension")
    plt.plot(f_ghz, db20(s11_fin), label="After L6-directed extension")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-10.0, linewidth=0.8)
    plt.axhline(L6_EXT_WORST_S11_MIN_DB, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("3Rx4 Nominal S11 - Final L6-Directed Extension")
    plt.ylim(-40, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"20_L6_directed_nominal_S11.png", dpi=220)
    plt.close(fig)

    s11_q, s21_q = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=60.0, cp_fF=60.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_q), label="S21 Q60/Cp60")
    plt.plot(f_ghz, db20(s11_q), label="S11 Q60/Cp60")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Magnitude (dB)")
    plt.title("3Rx4 Final Q60/Cp60 Diagnostic After L6-Directed Extension")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"21_L6_directed_Q60Cp60_diagnostic.png", dpi=220)
    plt.close(fig)



# =============================================================================
# 6H. Q60/Cp60 CELL-BY-CELL ROBUSTNESS TRIM
# =============================================================================

ROB_CELL_NOMINAL_RIPPLE_MAX_DB = 0.55
ROB_CELL_NOMINAL_BW_MIN_GHZ = 0.80
ROB_CELL_Q60_BW_MIN_GHZ = 0.78
ROB_CELL_TZ_TOL_GHZ = 0.025
ROB_CELL_Q60_IL_MAX_WORSEN_DB = 0.05
ROB_CELL_MIN_RIPPLE_IMPROVEMENT_DB = 1e-5

# Conservative local parameter windows around the current accepted cell values.
ROB_CELL_WINDOWS = (0.020, 0.010, 0.005)

# Start with the output-side cell because prior nominal optimization showed
# the strongest sensitivity there, then work inward.
ROB_CELL_ORDER = (3, 2, 1, 0)  # Cell 4 -> 3 -> 2 -> 1


def robustness_guard(
    before_v: dict,
    after_v: dict,
) -> bool:
    n = after_v["nominal"]
    qb = before_v["Q60_Cp60"]
    q = after_v["Q60_Cp60"]

    return (
        n["passband_ripple_dB"] <= ROB_CELL_NOMINAL_RIPPLE_MAX_DB
        and n["BW_3dB_GHz"] >= ROB_CELL_NOMINAL_BW_MIN_GHZ
        and q["BW_3dB_GHz"] >= ROB_CELL_Q60_BW_MIN_GHZ
        and abs(q["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= ROB_CELL_TZ_TOL_GHZ
        and abs(q["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= ROB_CELL_TZ_TOL_GHZ
        and q["minimum_IL_dB"] <= qb["minimum_IL_dB"] + ROB_CELL_Q60_IL_MAX_WORSEN_DB
    )


def robustness_score(v: dict) -> float:
    """
    Q60/Cp60 robustness score.

    Ripple is primary.
    Minimum insertion loss is secondary.
    Nominal ripple is a light tie-break term; hard nominal preservation
    is enforced separately by robustness_guard().
    """
    n = v["nominal"]
    q = v["Q60_Cp60"]
    return (
        1.00 * q["passband_ripple_dB"]
        + 0.25 * q["minimum_IL_dB"]
        + 0.08 * n["passband_ripple_dB"]
    )


def robust_optimize_one_cell(
    base: CellwiseDesign,
    cell_index: int,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
) -> Tuple[CellwiseDesign, dict]:
    """
    Optimize ONE cell only for Q60/Cp60 robustness.

    Adjustable within this cell:
        L3, L5, C1, L7a, L7b, L7c

    Frozen:
        all other cells
        L4
        L6

    Search uses coordinate descent with two passes.
    Every physical L7 segment continues to receive full Cp=60 fF.
    """
    names = ["L3_nH", "L5_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"]

    current = base
    vcur = verify_cellwise(current, low, high, f_ghz)
    current_score = robustness_score(vcur)

    for _ in range(2):
        improved_pass = False

        for pidx, name in enumerate(names):
            c0 = current.cells[cell_index]
            x0 = _cell_vector(c0)
            center = x0[pidx]
            lo_abs, hi_abs = _CELLWISE_BOUNDS[name]

            lo = max(lo_abs, center*(1-frac))
            hi = min(hi_abs, center*(1+frac))
            vals = np.linspace(lo, hi, 17)

            local_best = current
            local_v = vcur
            local_score = current_score

            for val in vals:
                x = x0.copy()
                x[pidx] = float(val)
                cand = replace_cell(current, cell_index, _cell_from_vector(x))
                vv = verify_cellwise(cand, low, high, f_ghz)

                if not robustness_guard(vcur, vv):
                    continue

                q0 = vcur["Q60_Cp60"]
                q1 = vv["Q60_Cp60"]

                # Require actual Q60 ripple improvement, not just weighted-score movement.
                if (
                    q0["passband_ripple_dB"] - q1["passband_ripple_dB"]
                    <= ROB_CELL_MIN_RIPPLE_IMPROVEMENT_DB
                ):
                    continue

                s = robustness_score(vv)
                if s < local_score - 1e-12:
                    local_best = cand
                    local_v = vv
                    local_score = s

            if local_score < current_score - 1e-12:
                current = local_best
                vcur = local_v
                current_score = local_score
                improved_pass = True

        if not improved_pass:
            break

    return current, vcur


def q60_cell_by_cell_robustness_trim(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Step-by-step Q60/Cp60 robustness trim.

    Three shrinking cycles:
        +/-2.0%
        +/-1.0%
        +/-0.5%

    Cell order:
        Cell 4 -> Cell 3 -> Cell 2 -> Cell 1

    A cell change is accepted only if:
      * Q60/Cp60 ripple improves by >1e-5 dB
      * nominal ripple remains <=0.55 dB
      * nominal BW >=0.80 GHz
      * Q60 BW >=0.78 GHz
      * TZs remain within +/-25 MHz
      * Q60 minimum IL worsens by no more than 0.05 dB at that step
    """
    current = start
    vcur = verify_cellwise(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("Q60/Cp60 CELL-BY-CELL ROBUSTNESS TRIM")
    print("="*78)

    n0 = vcur["nominal"]
    q0 = vcur["Q60_Cp60"]
    print(
        f"Robustness start: Q60 ripple={q0['passband_ripple_dB']:.6f} dB, "
        f"IL={q0['minimum_IL_dB']:.6f} dB, BW={q0['BW_3dB_GHz']:.6f} GHz | "
        f"nominal ripple={n0['passband_ripple_dB']:.6f} dB"
    )

    for cycle, frac in enumerate(ROB_CELL_WINDOWS, start=1):
        print(f"\nRobustness cycle {cycle}: cell-local window +/-{100*frac:.2f}%")
        cycle_improved = False

        for cell_index in ROB_CELL_ORDER:
            before = current
            vbefore = vcur

            q_before = vbefore["Q60_Cp60"]
            n_before = vbefore["nominal"]

            trial, vtrial = robust_optimize_one_cell(
                current, cell_index, frac, low, high, f_ghz
            )

            q_after = vtrial["Q60_Cp60"]
            n_after = vtrial["nominal"]

            ripple_improvement = (
                q_before["passband_ripple_dB"] - q_after["passband_ripple_dB"]
            )

            accept = (
                robustness_guard(vbefore, vtrial)
                and ripple_improvement > ROB_CELL_MIN_RIPPLE_IMPROVEMENT_DB
            )

            if accept:
                current = trial
                vcur = vtrial
                cycle_improved = True
                print(
                    f"Cell {cell_index+1}: ACCEPT | "
                    f"Q60 ripple {q_before['passband_ripple_dB']:.6f} "
                    f"-> {q_after['passband_ripple_dB']:.6f} dB | "
                    f"IL {q_before['minimum_IL_dB']:.6f} "
                    f"-> {q_after['minimum_IL_dB']:.6f} dB | "
                    f"nom={n_after['passband_ripple_dB']:.6f} dB"
                )
            else:
                current = before
                vcur = vbefore
                print(
                    f"Cell {cell_index+1}: REJECT | "
                    f"Q60 ripple remains {q_before['passband_ripple_dB']:.6f} dB | "
                    f"nom={n_before['passband_ripple_dB']:.6f} dB"
                )

            history.append({
                "cycle": cycle,
                "window_percent": 100*frac,
                "cell": cell_index+1,
                "accepted": bool(accept),
                "Q60_ripple_before_dB": q_before["passband_ripple_dB"],
                "Q60_ripple_after_dB": (
                    vcur["Q60_Cp60"]["passband_ripple_dB"]
                ),
                "Q60_IL_before_dB": q_before["minimum_IL_dB"],
                "Q60_IL_after_dB": vcur["Q60_Cp60"]["minimum_IL_dB"],
                "nominal_ripple_before_dB": n_before["passband_ripple_dB"],
                "nominal_ripple_after_dB": vcur["nominal"]["passband_ripple_dB"],
                "design_after": current.to_dict(),
            })

        if not cycle_improved:
            print("No cell improved in this cycle; robustness trim stopped.")
            break

    return current, vcur, history


def plot_robustness_cellwise_sparams(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    pre_robust: CellwiseDesign,
    final: CellwiseDesign,
) -> None:
    if plt is None:
        return

    # Q60/Cp60 S21 comparison.
    s11_pre_q, s21_pre_q = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, pre_robust, low, high, qind=60.0, cp_fF=60.0
    )
    s11_fin_q, s21_fin_q = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=60.0, cp_fF=60.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_pre_q), label="Before robustness trim")
    plt.plot(f_ghz, db20(s21_fin_q), label="After robustness trim")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Q60/Cp60 S21 - Cell-by-Cell Robustness Trim")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"23_Q60Cp60_cellwise_S21_before_after.png", dpi=220)
    plt.close(fig)

    # Q60/Cp60 S11 comparison.
    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s11_pre_q), label="Before robustness trim")
    plt.plot(f_ghz, db20(s11_fin_q), label="After robustness trim")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-10.0, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("3Rx4 Q60/Cp60 S11 - Cell-by-Cell Robustness Trim")
    plt.ylim(-40, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"24_Q60Cp60_cellwise_S11_before_after.png", dpi=220)
    plt.close(fig)

    # Nominal preservation check.
    s11_pre_n, s21_pre_n = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, pre_robust, low, high, qind=None, cp_fF=0.0
    )
    s11_fin_n, s21_fin_n = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, final, low, high, qind=None, cp_fF=0.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_pre_n), label="Nominal before robustness trim")
    plt.plot(f_ghz, db20(s21_fin_n), label="Nominal after robustness trim")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Nominal S21 Preservation After Q60/Cp60 Trim")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"25_nominal_preservation_after_robustness.png", dpi=220)
    plt.close(fig)



# =============================================================================
# 6I. BALANCED ROBUSTNESS CHECKPOINT SELECTION + Q80/Cp40
# =============================================================================

BAL_Q60_RIPPLE_TARGET_DB = 0.82
BAL_Q60_IL_TARGET_DB = 1.50
BAL_NOM_RIPPLE_TARGET_DB = 0.55
BAL_NOM_BW_MIN_GHZ = 0.80
BAL_Q60_BW_MIN_GHZ = 0.78
BAL_TZ_TOL_GHZ = 0.025


def verify_cellwise_extended(
    design: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
) -> dict:
    """
    Extended verification set:
      nominal
      Q60/Cp60
      Q80/Cp40
    """
    out = {}
    for name, q, cp in (
        ("nominal", None, 0.0),
        ("Q60_Cp60", 60.0, 60.0),
        ("Q80_Cp40", 80.0, 40.0),
    ):
        s11, s21 = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, design, low, high, qind=q, cp_fF=cp
        )
        out[name] = metrics(f_ghz, s11, s21)
    return out


def balanced_checkpoint_score(v: dict) -> float:
    """
    Select a practical compromise checkpoint rather than the absolute
    minimum Q60 ripple point.

    Priority:
      1) keep Q60 ripple near/below 0.82 dB
      2) avoid Q60 IL > 1.50 dB
      3) preserve nominal ripple <= 0.55 dB
      4) lightly reward Q80/Cp40 performance
    """
    n = v["nominal"]
    q60 = v["Q60_Cp60"]
    q80 = v["Q80_Cp40"]

    rp60_ex = max(0.0, q60["passband_ripple_dB"] - BAL_Q60_RIPPLE_TARGET_DB)
    il60_ex = max(0.0, q60["minimum_IL_dB"] - BAL_Q60_IL_TARGET_DB)
    nr_ex = max(0.0, n["passband_ripple_dB"] - BAL_NOM_RIPPLE_TARGET_DB)

    return (
        1.00 * q60["passband_ripple_dB"]
        + 0.45 * q60["minimum_IL_dB"]
        + 0.18 * n["passband_ripple_dB"]
        + 0.12 * q80["passband_ripple_dB"]
        + 0.08 * q80["minimum_IL_dB"]
        + 3.0 * rp60_ex
        + 4.0 * il60_ex
        + 5.0 * nr_ex
    )


def balanced_checkpoint_guard(v: dict) -> bool:
    n = v["nominal"]
    q60 = v["Q60_Cp60"]
    return (
        n["passband_ripple_dB"] <= BAL_NOM_RIPPLE_TARGET_DB
        and n["BW_3dB_GHz"] >= BAL_NOM_BW_MIN_GHZ
        and q60["BW_3dB_GHz"] >= BAL_Q60_BW_MIN_GHZ
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= BAL_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= BAL_TZ_TOL_GHZ
    )


def collect_and_select_balanced_checkpoint(
    nominal_final: CellwiseDesign,
    robustness_history: list,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Evaluate the nominal-final checkpoint plus every accepted robustness checkpoint.
    Choose the feasible point with minimum balanced score.
    """
    candidates = [("nominal_final", nominal_final)]

    for i, h in enumerate(robustness_history):
        if h.get("accepted") and "design_after" in h:
            dct = h["design_after"]
            cells = []
            for k in ("cell1", "cell2", "cell3", "cell4"):
                c = dct["cells"][k]
                cells.append(CellParams(
                    L3_nH=c["L3_nH"],
                    L5_nH=c["L5_nH"],
                    C1_pF=c["C1_pF"],
                    L7a_nH=c["L7a_nH"],
                    L7b_nH=c["L7b_nH"],
                    L7c_nH=c["L7c_nH"],
                ))
            d = CellwiseDesign(
                cells=tuple(cells),
                L4_nH=dct["L4_nH"],
                L6_nH=dct["L6_nH"],
            )
            candidates.append((f"accepted_{i+1}_cycle{h['cycle']}_cell{h['cell']}", d))

    rows = []
    feasible = []

    for label, d in candidates:
        v = verify_cellwise_extended(d, low, high, f_ghz)
        s = balanced_checkpoint_score(v)
        ok = balanced_checkpoint_guard(v)

        n = v["nominal"]
        q60 = v["Q60_Cp60"]
        q80 = v["Q80_Cp40"]

        rows.append({
            "checkpoint": label,
            "feasible": ok,
            "score": s,
            "nominal_ripple_dB": n["passband_ripple_dB"],
            "nominal_IL_dB": n["minimum_IL_dB"],
            "nominal_BW_GHz": n["BW_3dB_GHz"],
            "Q60Cp60_ripple_dB": q60["passband_ripple_dB"],
            "Q60Cp60_IL_dB": q60["minimum_IL_dB"],
            "Q60Cp60_BW_GHz": q60["BW_3dB_GHz"],
            "Q80Cp40_ripple_dB": q80["passband_ripple_dB"],
            "Q80Cp40_IL_dB": q80["minimum_IL_dB"],
            "Q80Cp40_BW_GHz": q80["BW_3dB_GHz"],
            "design": d.to_dict(),
        })

        if ok:
            feasible.append((s, label, d, v))

    if not feasible:
        raise RuntimeError("No feasible checkpoint for balanced selection")

    feasible.sort(key=lambda x: x[0])
    return feasible[0], pd.DataFrame(rows)


def plot_balanced_robustness(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    nominal_final: CellwiseDesign,
    selected: CellwiseDesign,
) -> None:
    if plt is None:
        return

    # Q60/Cp60 comparison
    s11_a, s21_a = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, nominal_final, low, high, qind=60.0, cp_fF=60.0
    )
    s11_b, s21_b = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, selected, low, high, qind=60.0, cp_fF=60.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_a), label="Nominal-final checkpoint")
    plt.plot(f_ghz, db20(s21_b), label="Balanced selected")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("3Rx4 Q60/Cp60 S21 - Balanced Checkpoint Selection")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"27_balanced_Q60Cp60_S21.png", dpi=220)
    plt.close(fig)

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s11_a), label="Nominal-final checkpoint")
    plt.plot(f_ghz, db20(s11_b), label="Balanced selected")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.axhline(-10.0, linewidth=0.8)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S11 (dB)")
    plt.title("3Rx4 Q60/Cp60 S11 - Balanced Checkpoint Selection")
    plt.ylim(-40, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"28_balanced_Q60Cp60_S11.png", dpi=220)
    plt.close(fig)

    # Q80/Cp40 diagnostic
    s11_80, s21_80 = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, selected, low, high, qind=80.0, cp_fF=40.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_80), label="S21 Q80/Cp40")
    plt.plot(f_ghz, db20(s11_80), label="S11 Q80/Cp40")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Magnitude (dB)")
    plt.title("3Rx4 Balanced Selected - Q80/Cp40 Diagnostic")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"29_balanced_Q80Cp40_S11_S21.png", dpi=220)
    plt.close(fig)

    # Nominal preservation
    s11_n, s21_n = simulate_dfr_3rx4_cellwise(
        f_ghz*1e9, selected, low, high, qind=None, cp_fF=0.0
    )

    fig = plt.figure(figsize=(9.5, 5.6))
    plt.plot(f_ghz, db20(s21_n), label="Balanced selected nominal S21")
    plt.plot(f_ghz, db20(s11_n), label="Balanced selected nominal S11")
    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("Magnitude (dB)")
    plt.title("3Rx4 Balanced Selected - Nominal Diagnostic")
    plt.ylim(-80, 2)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"30_balanced_nominal_S11_S21.png", dpi=220)
    plt.close(fig)



# =============================================================================
# 6J. ADS 3Rx4 REFERENCE REPRODUCTION + DIRECT PERFORMANCE COMPARISON
# =============================================================================

# ADS reference values supplied by the user.
#
# NOTE:
#   ADS schematic segment values are L7a=L7b=L7c=0.247 nH.
#   Their arithmetic sum is 0.741 nH, while the design note states
#   L7(total)=0.7405 nH.  For ADS reproduction we use the actual
#   per-element schematic values (0.247 nH each), because those are
#   what ADS directly simulates.
ADS_REF = {
    "L3_nH": 0.269,
    "L4_nH": 0.559,
    "L5_nH": 0.180,
    "L6_nH": 0.988,
    "L7_total_stated_nH": 0.7405,
    "L7a_nH": 0.247,
    "L7b_nH": 0.247,
    "L7c_nH": 0.247,
    "C1_pF": 0.7326,
}


def make_ads_reference_3rx4() -> CellwiseDesign:
    """
    Build the exact repeated-cell ADS reference circuit.

    All four 3R cells use the same:
        L3 = 0.269 nH
        L5 = 0.180 nH
        C1 = 0.7326 pF
        L7a=L7b=L7c=0.247 nH

    Global terminal inductors:
        L4 = 0.559 nH, first cell only
        L6 = 0.988 nH, final cell only

    Q/Cp implementation remains identical to the Python ADS-surrogate model:
        each physical inductor receives the full Cp value in non-ideal cases.
    """
    c = CellParams(
        L3_nH=ADS_REF["L3_nH"],
        L5_nH=ADS_REF["L5_nH"],
        C1_pF=ADS_REF["C1_pF"],
        L7a_nH=ADS_REF["L7a_nH"],
        L7b_nH=ADS_REF["L7b_nH"],
        L7c_nH=ADS_REF["L7c_nH"],
    )
    return CellwiseDesign(
        cells=(c, c, c, c),
        L4_nH=ADS_REF["L4_nH"],
        L6_nH=ADS_REF["L6_nH"],
    )


def ads_reference_verify_3cases(
    design: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
) -> dict:
    """
    Reproduce the three ADS comparison cases:

      1) Nominal: ideal external inductors, Cp=0
      2) Qind=80, Cp=40 fF
      3) Qind=60, Cp=60 fF

    Important:
      every physical L3/L4/L5/L6/L7a/L7b/L7c receives the specified Cp.
      Thus each of the three L7 segments has its own full Cp.
    """
    scenarios = (
        ("nominal", None, 0.0),
        ("Q80_Cp40", 80.0, 40.0),
        ("Q60_Cp60", 60.0, 60.0),
    )
    out = {}
    for name, q, cp in scenarios:
        s11, s21 = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, design, low, high, qind=q, cp_fF=cp
        )
        out[name] = metrics(f_ghz, s11, s21)
    return out


def _metric_row(label: str, scenario: str, m: dict) -> dict:
    return {
        "design": label,
        "scenario": scenario,
        "ripple_dB": m["passband_ripple_dB"],
        "minimum_IL_dB": m["minimum_IL_dB"],
        "worst_passband_IL_dB": m["worst_passband_IL_dB"],
        "BW_3dB_GHz": m["BW_3dB_GHz"],
        "worst_S11_dB": m["worst_S11_dB"],
        "S21_center_dB": m["S21_center_dB"],
        "TZL_GHz": m["TZL"]["GHz"],
        "TZU_GHz": m["TZU"]["GHz"],
        "lower_stopband_rejection_dB": m["lower_stopband_min_rejection_dB"],
        "upper_stopband_rejection_dB": m["upper_stopband_min_rejection_dB"],
    }


def build_ads_vs_python_comparison(
    ads_metrics: dict,
    optimized_metrics: dict,
) -> pd.DataFrame:
    """
    Build one table containing:
      ADS-reference surrogate
      Python balanced-selected

    and explicit improvement rows:
      positive ripple/IL improvement means the optimized design is better.
      positive S11 improvement means worst S11 became more negative.
    """
    rows = []

    for scenario in ("nominal", "Q80_Cp40", "Q60_Cp60"):
        a = ads_metrics[scenario]
        o = optimized_metrics[scenario]

        rows.append(_metric_row("ADS_reference", scenario, a))
        rows.append(_metric_row("Python_balanced_selected", scenario, o))

        rows.append({
            "design": "Improvement_selected_minus_ADS",
            "scenario": scenario,
            "ripple_dB": a["passband_ripple_dB"] - o["passband_ripple_dB"],
            "minimum_IL_dB": a["minimum_IL_dB"] - o["minimum_IL_dB"],
            "worst_passband_IL_dB":
                a["worst_passband_IL_dB"] - o["worst_passband_IL_dB"],
            "BW_3dB_GHz": o["BW_3dB_GHz"] - a["BW_3dB_GHz"],
            "worst_S11_dB": a["worst_S11_dB"] - o["worst_S11_dB"],
            "S21_center_dB": o["S21_center_dB"] - a["S21_center_dB"],
            "TZL_GHz": o["TZL"]["GHz"] - a["TZL"]["GHz"],
            "TZU_GHz": o["TZU"]["GHz"] - a["TZU"]["GHz"],
            "lower_stopband_rejection_dB":
                o["lower_stopband_min_rejection_dB"]
                - a["lower_stopband_min_rejection_dB"],
            "upper_stopband_rejection_dB":
                o["upper_stopband_min_rejection_dB"]
                - a["upper_stopband_min_rejection_dB"],
        })

    return pd.DataFrame(rows)


def plot_ads_reference_three_cases(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    ads_design: CellwiseDesign,
) -> None:
    """
    Produce one S11/S21 image for each ADS-reference case.
    """
    if plt is None:
        return

    cases = (
        ("Nominal", None, 0.0, "33_ADS_reference_nominal_S11_S21.png"),
        ("Q80/Cp40", 80.0, 40.0, "34_ADS_reference_Q80Cp40_S11_S21.png"),
        ("Q60/Cp60", 60.0, 60.0, "35_ADS_reference_Q60Cp60_S11_S21.png"),
    )

    for title, q, cp, filename in cases:
        s11, s21 = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, ads_design, low, high, qind=q, cp_fF=cp
        )

        fig = plt.figure(figsize=(9.5, 5.6))
        plt.plot(f_ghz, db20(s21), label=f"S21 {title}")
        plt.plot(f_ghz, db20(s11), label=f"S11 {title}")
        plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
        plt.axhline(-10.0, linewidth=0.8)
        plt.xlabel("Frequency (GHz)")
        plt.ylabel("Magnitude (dB)")
        plt.title(f"3Rx4 ADS-Reference Reproduction - {title}")
        plt.ylim(-80, 2)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        fig.savefig(outdir/filename, dpi=220)
        plt.close(fig)


def plot_ads_vs_selected_s21(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    ads_design: CellwiseDesign,
    selected: CellwiseDesign,
) -> None:
    """
    Direct S21 overlay: ADS reference vs Python balanced-selected,
    separately for each scenario.
    """
    if plt is None:
        return

    cases = (
        ("Nominal", None, 0.0, "36_compare_nominal_ADSref_vs_selected_S21.png"),
        ("Q80/Cp40", 80.0, 40.0, "37_compare_Q80Cp40_ADSref_vs_selected_S21.png"),
        ("Q60/Cp60", 60.0, 60.0, "38_compare_Q60Cp60_ADSref_vs_selected_S21.png"),
    )

    for title, q, cp, filename in cases:
        _, s21_ads = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, ads_design, low, high, qind=q, cp_fF=cp
        )
        _, s21_opt = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, selected, low, high, qind=q, cp_fF=cp
        )

        fig = plt.figure(figsize=(9.5, 5.6))
        plt.plot(f_ghz, db20(s21_ads), label="ADS-reference parameters")
        plt.plot(f_ghz, db20(s21_opt), label="Python balanced-selected")
        plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
        plt.xlabel("Frequency (GHz)")
        plt.ylabel("S21 (dB)")
        plt.title(f"3Rx4 {title} - ADS Reference vs Python Improvement")
        plt.ylim(-80, 2)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        fig.savefig(outdir/filename, dpi=220)
        plt.close(fig)



# =============================================================================
# 6K. FINAL PASSBAND ROBUSTNESS OPTIMIZATION WITH 50-dB FAR-STOP GUARDRAIL
# =============================================================================

FINAL_REJ_MIN_DB = 50.0
FINAL_NOM_RIPPLE_MAX_DB = 0.56
FINAL_NOM_BW_MIN_GHZ = 0.80
FINAL_Q80_BW_MIN_GHZ = 0.80
FINAL_Q60_BW_MIN_GHZ = 0.78
FINAL_TZ_TOL_GHZ = 0.025
FINAL_Q60_S11_TARGET_DB = -8.0
FINAL_Q60_IL_TARGET_DB = 1.50
FINAL_Q60_RIPPLE_TARGET_DB = 0.82
FINAL_CELL_WINDOWS = (0.010, 0.005)
FINAL_CELL_ORDER = (3, 2, 1, 0)  # Cell 4 -> 3 -> 2 -> 1


def final_passband_guard(v: dict) -> bool:
    """Hard constraints; rejection is a guardrail, not an optimization objective."""
    n = v['nominal']
    q80 = v['Q80_Cp40']
    q60 = v['Q60_Cp60']

    for m in (n, q80, q60):
        if m['lower_stopband_min_rejection_dB'] < FINAL_REJ_MIN_DB:
            return False
        if m['upper_stopband_min_rejection_dB'] < FINAL_REJ_MIN_DB:
            return False

    return (
        n['passband_ripple_dB'] <= FINAL_NOM_RIPPLE_MAX_DB
        and n['BW_3dB_GHz'] >= FINAL_NOM_BW_MIN_GHZ
        and q80['BW_3dB_GHz'] >= FINAL_Q80_BW_MIN_GHZ
        and q60['BW_3dB_GHz'] >= FINAL_Q60_BW_MIN_GHZ
        and abs(q60['TZL']['GHz'] - TZ_TARGETS_GHZ[0]) <= FINAL_TZ_TOL_GHZ
        and abs(q60['TZU']['GHz'] - TZ_TARGETS_GHZ[1]) <= FINAL_TZ_TOL_GHZ
    )


def final_passband_score(v: dict) -> float:
    """
    Optimize passband robustness only.

    Main terms:
      Q60/Cp60 ripple
      Q60/Cp60 minimum IL
      Q60/Cp60 worst-S11 penalty

    Q80/Cp40 and nominal are light preservation/tie-break terms.
    Far-stop rejection is intentionally NOT rewarded above 50 dB.
    """
    n = v['nominal']
    q80 = v['Q80_Cp40']
    q60 = v['Q60_Cp60']

    ripple_excess = max(0.0, q60['passband_ripple_dB'] - FINAL_Q60_RIPPLE_TARGET_DB)
    il_excess = max(0.0, q60['minimum_IL_dB'] - FINAL_Q60_IL_TARGET_DB)
    s11_excess = max(0.0, q60['worst_S11_dB'] - FINAL_Q60_S11_TARGET_DB)

    return (
        1.00*q60['passband_ripple_dB']
        + 0.55*q60['minimum_IL_dB']
        + 0.35*s11_excess
        + 0.18*q80['passband_ripple_dB']
        + 0.08*q80['minimum_IL_dB']
        + 0.10*n['passband_ripple_dB']
        + 2.0*ripple_excess
        + 2.0*il_excess
    )


def _final_optimize_one_cell(
    base: CellwiseDesign,
    cell_index: int,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    names = ['L3_nH','L5_nH','C1_pF','L7a_nH','L7b_nH','L7c_nH']
    current = base
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    best_d, best_v = current, vcur
    best_score = final_passband_score(vcur) if final_passband_guard(vcur) else float('inf')

    # Two coordinate sweeps per cell.
    for _ in range(2):
        improved = False
        for pidx, name in enumerate(names):
            c0 = best_d.cells[cell_index]
            x0 = _cell_vector(c0)
            center = x0[pidx]
            lo_abs, hi_abs = _CELLWISE_BOUNDS[name]
            vals = np.linspace(
                max(lo_abs, center*(1-frac)),
                min(hi_abs, center*(1+frac)),
                17,
            )

            local_d, local_v, local_score = best_d, best_v, best_score
            for val in vals:
                x = x0.copy(); x[pidx] = float(val)
                cand = replace_cell(best_d, cell_index, _cell_from_vector(x))
                vv = verify_cellwise_extended(cand, low, high, f_ghz)
                if not final_passband_guard(vv):
                    continue
                sc = final_passband_score(vv)
                if sc < local_score - 1e-10:
                    local_d, local_v, local_score = cand, vv, sc

            if local_score < best_score - 1e-10:
                best_d, best_v, best_score = local_d, local_v, local_score
                improved = True
        if not improved:
            break

    return best_d, best_v, best_score


def _final_terminal_polish(
    base: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """Small L4/L6 terminal polish after all cells are frozen."""
    v0 = verify_cellwise_extended(base, low, high, f_ghz)
    best_d, best_v = base, v0
    best_score = final_passband_score(v0) if final_passband_guard(v0) else float('inf')

    l4s = np.linspace(base.L4_nH*0.996, base.L4_nH*1.004, 25)
    l6s = np.linspace(base.L6_nH*0.994, base.L6_nH*1.006, 31)
    for l4 in l4s:
        for l6 in l6s:
            cand = replace_terminals(base, L4_nH=float(l4), L6_nH=float(l6))
            vv = verify_cellwise_extended(cand, low, high, f_ghz)
            if not final_passband_guard(vv):
                continue
            sc = final_passband_score(vv)
            if sc < best_score - 1e-10:
                best_d, best_v, best_score = cand, vv, sc
    return best_d, best_v, best_score


def final_passband_robustness_50dB(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """Final cell-by-cell passband robustness stage with 50-dB stopband floor."""
    start_v = verify_cellwise_extended(start, low, high, f_ghz)
    start_score = final_passband_score(start_v)
    current, vcur = start, start_v
    history = []

    print('\n' + '='*78)
    print('FINAL PASSBAND ROBUSTNESS WITH 50-dB FAR-STOP GUARDRAIL')
    print('='*78)
    print(
        f"Start: Q60 ripple={start_v['Q60_Cp60']['passband_ripple_dB']:.6f} dB, "
        f"IL={start_v['Q60_Cp60']['minimum_IL_dB']:.6f} dB, "
        f"S11worst={start_v['Q60_Cp60']['worst_S11_dB']:.6f} dB, "
        f"far-rej=({start_v['Q60_Cp60']['lower_stopband_min_rejection_dB']:.3f}, "
        f"{start_v['Q60_Cp60']['upper_stopband_min_rejection_dB']:.3f}) dB"
    )

    # Since the selected starting point may be just below 50 dB on one side,
    # search all local cell moves for the first feasible and lower-score point.
    for cycle, frac in enumerate(FINAL_CELL_WINDOWS, start=1):
        print(f"\nCycle {cycle}: cell window +/-{100*frac:.2f}%")
        for cell_index in FINAL_CELL_ORDER:
            before = current
            vb = verify_cellwise_extended(before, low, high, f_ghz)
            trial, vt, sc = _final_optimize_one_cell(
                before, cell_index, frac, low, high, f_ghz
            )
            before_feasible = final_passband_guard(vb)
            before_score = final_passband_score(vb) if before_feasible else float('inf')
            accept = final_passband_guard(vt) and sc < before_score - 1e-8

            if accept:
                current, vcur = trial, vt
                print(
                    f"Cell {cell_index+1}: ACCEPT | "
                    f"Q60 ripple {vb['Q60_Cp60']['passband_ripple_dB']:.6f} -> "
                    f"{vt['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                    f"IL {vb['Q60_Cp60']['minimum_IL_dB']:.6f} -> "
                    f"{vt['Q60_Cp60']['minimum_IL_dB']:.6f} dB | "
                    f"S11 {vb['Q60_Cp60']['worst_S11_dB']:.3f} -> "
                    f"{vt['Q60_Cp60']['worst_S11_dB']:.3f} dB | "
                    f"rej=({vt['Q60_Cp60']['lower_stopband_min_rejection_dB']:.2f}, "
                    f"{vt['Q60_Cp60']['upper_stopband_min_rejection_dB']:.2f})"
                )
            else:
                print(f"Cell {cell_index+1}: REJECT")

            history.append({
                'cycle': cycle,
                'cell': cell_index+1,
                'accepted': bool(accept),
                'design_after': current.to_dict(),
                'metrics_after': verify_cellwise_extended(current, low, high, f_ghz),
            })

    # Final terminal polish, cells frozen.
    terminal_d, terminal_v, terminal_score = _final_terminal_polish(
        current, low, high, f_ghz
    )
    current_feasible = final_passband_guard(vcur)
    current_score = final_passband_score(vcur) if current_feasible else float('inf')
    terminal_accept = final_passband_guard(terminal_v) and terminal_score < current_score - 1e-8
    if terminal_accept:
        current, vcur = terminal_d, terminal_v
        print('Terminal L4/L6 polish: ACCEPT')
    else:
        print('Terminal L4/L6 polish: REJECT')

    success = final_passband_guard(vcur)
    return current, vcur, history, success


def plot_final_passband_50dB(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    before: CellwiseDesign,
    after: CellwiseDesign,
):
    if plt is None:
        return
    for title, q, cp, fname in (
        ('Nominal', None, 0.0, '41_final50dB_nominal_S11_S21.png'),
        ('Q80/Cp40', 80.0, 40.0, '42_final50dB_Q80Cp40_S11_S21.png'),
        ('Q60/Cp60', 60.0, 60.0, '43_final50dB_Q60Cp60_S11_S21.png'),
    ):
        s11b, s21b = simulate_dfr_3rx4_cellwise(f_ghz*1e9, before, low, high, qind=q, cp_fF=cp)
        s11a, s21a = simulate_dfr_3rx4_cellwise(f_ghz*1e9, after, low, high, qind=q, cp_fF=cp)
        fig = plt.figure(figsize=(9.5,5.6))
        plt.plot(f_ghz, db20(s21b), label='Before final robustness trim S21')
        plt.plot(f_ghz, db20(s21a), label='After final robustness trim S21')
        plt.plot(f_ghz, db20(s11a), label='After final robustness trim S11')
        plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
        plt.axhline(-50.0, linewidth=0.8)
        plt.xlabel('Frequency (GHz)'); plt.ylabel('Magnitude (dB)')
        plt.title(f'3Rx4 Final 50-dB-Guardrail Robustness - {title}')
        plt.ylim(-80,2); plt.grid(True); plt.legend(); plt.tight_layout()
        fig.savefig(outdir/fname, dpi=220); plt.close(fig)



# =============================================================================
# 6L. FINAL Q60 LOWER-STOPBAND MICRO-RECOVERY TRIM
# =============================================================================

RECOVERY_TARGET_DB = 50.0
RECOVERY_WINDOW = 0.003          # +/-0.3%
RECOVERY_FINE_WINDOW = 0.001     # +/-0.1% if needed
RECOVERY_CELL_ORDER = (3, 2, 1, 0)   # Cell 4 -> 3 -> 2 -> 1
RECOVERY_NAMES = ("L3_nH", "L7a_nH", "L7b_nH", "L7c_nH")

# Strict passband-preservation limits.
RECOVERY_NOM_RIPPLE_MAX_DB = 0.54
RECOVERY_Q80_RIPPLE_MAX_DB = 0.68
RECOVERY_Q60_RIPPLE_MAX_DB = 0.83
RECOVERY_Q60_IL_MAX_DB = 1.53
RECOVERY_NOM_BW_MIN_GHZ = 0.80
RECOVERY_Q80_BW_MIN_GHZ = 0.80
RECOVERY_Q60_BW_MIN_GHZ = 0.78
RECOVERY_TZ_TOL_GHZ = 0.025

# Keep all already-good far-stop sides at or above 50 dB.
RECOVERY_OTHER_REJ_MIN_DB = 50.0


def recovery_preservation_guard(v: dict) -> bool:
    """
    Hard preservation guard.

    Q60 lower far-stop rejection is intentionally excluded here because it is
    the quantity being recovered from ~49.76 dB to >=50 dB.
    """
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]

    return (
        n["passband_ripple_dB"] <= RECOVERY_NOM_RIPPLE_MAX_DB
        and q80["passband_ripple_dB"] <= RECOVERY_Q80_RIPPLE_MAX_DB
        and q60["passband_ripple_dB"] <= RECOVERY_Q60_RIPPLE_MAX_DB
        and q60["minimum_IL_dB"] <= RECOVERY_Q60_IL_MAX_DB
        and n["BW_3dB_GHz"] >= RECOVERY_NOM_BW_MIN_GHZ
        and q80["BW_3dB_GHz"] >= RECOVERY_Q80_BW_MIN_GHZ
        and q60["BW_3dB_GHz"] >= RECOVERY_Q60_BW_MIN_GHZ
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= RECOVERY_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= RECOVERY_TZ_TOL_GHZ

        # Preserve all far-stop sides that are already >=50 dB.
        and n["lower_stopband_min_rejection_dB"] >= RECOVERY_OTHER_REJ_MIN_DB
        and n["upper_stopband_min_rejection_dB"] >= RECOVERY_OTHER_REJ_MIN_DB
        and q80["lower_stopband_min_rejection_dB"] >= RECOVERY_OTHER_REJ_MIN_DB
        and q80["upper_stopband_min_rejection_dB"] >= RECOVERY_OTHER_REJ_MIN_DB
        and q60["upper_stopband_min_rejection_dB"] >= RECOVERY_OTHER_REJ_MIN_DB
    )


def recovery_tiebreak_score(v: dict) -> float:
    """Lower is better once rejection is comparable or the 50-dB target is met."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        1.00*q60["passband_ripple_dB"]
        + 0.45*q60["minimum_IL_dB"]
        + 0.15*q80["passband_ripple_dB"]
        + 0.08*n["passband_ripple_dB"]
        + 0.05*max(0.0, q60["worst_S11_dB"] + 8.0)
    )


def _recovery_candidate_better(v_new: dict, v_old: dict) -> bool:
    """
    Lexicographic recovery rule:

    1) If old point is below 50 dB, first maximize Q60 lower rejection.
    2) Once >=50 dB is reached, never fall below 50 dB again.
    3) Among >=50-dB points, minimize passband tiebreak score.
    """
    r_new = v_new["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
    r_old = v_old["Q60_Cp60"]["lower_stopband_min_rejection_dB"]

    old_met = r_old >= RECOVERY_TARGET_DB
    new_met = r_new >= RECOVERY_TARGET_DB

    if old_met:
        if not new_met:
            return False
        return recovery_tiebreak_score(v_new) < recovery_tiebreak_score(v_old) - 1e-10

    if new_met:
        return True

    # Still below target: require a meaningful rejection increase and do not
    # allow passband score to degrade excessively.
    return (
        r_new > r_old + 1e-4
        and recovery_tiebreak_score(v_new) <= recovery_tiebreak_score(v_old) + 0.01
    )


def _micro_trim_one_cell(
    base: CellwiseDesign,
    cell_index: int,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    One-cell micro trim. Only L3 and the three physical L7 segments can move.
    L5, C1, every other cell, L4 and L6 are frozen.
    """
    current = base
    vcur = verify_cellwise_extended(current, low, high, f_ghz)

    # Two coordinate passes are enough at this micro-trim scale.
    for _ in range(2):
        improved = False

        for name in RECOVERY_NAMES:
            c0 = current.cells[cell_index]
            x0 = _cell_vector(c0)
            names_all = ["L3_nH", "L5_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"]
            pidx = names_all.index(name)
            center = x0[pidx]
            lo_abs, hi_abs = _CELLWISE_BOUNDS[name]

            vals = np.linspace(
                max(lo_abs, center*(1-frac)),
                min(hi_abs, center*(1+frac)),
                25,
            )

            local = current
            vlocal = vcur

            for val in vals:
                x = x0.copy()
                x[pidx] = float(val)
                cand = replace_cell(current, cell_index, _cell_from_vector(x))
                vv = verify_cellwise_extended(cand, low, high, f_ghz)

                if not recovery_preservation_guard(vv):
                    continue

                if _recovery_candidate_better(vv, vlocal):
                    local, vlocal = cand, vv

            if local is not current:
                current, vcur = local, vlocal
                improved = True

                # Stop immediately once the 50-dB target is crossed.
                if vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= RECOVERY_TARGET_DB:
                    return current, vcur

        if not improved:
            break

    return current, vcur


def final_lower_stopband_recovery(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Recover Q60/Cp60 lower far-stop rejection to >=50 dB with minimal movement.

    Pass 1: +/-0.3%
    Pass 2: +/-0.1% only if the target was not reached.

    Cell order:
      Cell 4 -> Cell 3 -> Cell 2 -> Cell 1

    Only L3 and L7a/L7b/L7c are allowed to move.
    """
    current = start
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("FINAL Q60 LOWER-STOPBAND RECOVERY TRIM")
    print("="*78)

    q0 = vcur["Q60_Cp60"]
    print(
        f"Start: lower far-rej={q0['lower_stopband_min_rejection_dB']:.6f} dB, "
        f"ripple={q0['passband_ripple_dB']:.6f} dB, "
        f"IL={q0['minimum_IL_dB']:.6f} dB"
    )

    if q0["lower_stopband_min_rejection_dB"] >= RECOVERY_TARGET_DB:
        print("Already >=50 dB; no recovery trim required.")
        return current, vcur, history, True

    for pass_name, frac in (("coarse_micro", RECOVERY_WINDOW),
                            ("fine_micro", RECOVERY_FINE_WINDOW)):
        print(f"\n{pass_name}: cell-local window +/-{100*frac:.3f}%")

        for cell_index in RECOVERY_CELL_ORDER:
            before = current
            vb = vcur
            trial, vt = _micro_trim_one_cell(
                current, cell_index, frac, low, high, f_ghz
            )

            rb = vb["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
            rt = vt["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
            accept = (
                recovery_preservation_guard(vt)
                and _recovery_candidate_better(vt, vb)
            )

            if accept:
                current, vcur = trial, vt
                print(
                    f"Cell {cell_index+1}: ACCEPT | Q60 lower far-rej "
                    f"{rb:.6f} -> {rt:.6f} dB | "
                    f"ripple={vt['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                    f"IL={vt['Q60_Cp60']['minimum_IL_dB']:.6f} dB | "
                    f"nom={vt['nominal']['passband_ripple_dB']:.6f} dB"
                )
            else:
                current, vcur = before, vb
                print(
                    f"Cell {cell_index+1}: REJECT | Q60 lower far-rej "
                    f"remains {rb:.6f} dB"
                )

            history.append({
                "pass": pass_name,
                "window_percent": 100*frac,
                "cell": cell_index+1,
                "accepted": bool(accept),
                "Q60_lower_far_rej_before_dB": rb,
                "Q60_lower_far_rej_after_dB":
                    vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "design_after": current.to_dict(),
                "metrics_after": vcur,
            })

            if vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= RECOVERY_TARGET_DB:
                print(
                    f"TARGET REACHED: Q60/Cp60 lower far-stop rejection "
                    f"= {vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB"
                )
                return current, vcur, history, True

    success = vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= RECOVERY_TARGET_DB
    return current, vcur, history, success


def plot_lower_stopband_recovery(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    before: CellwiseDesign,
    after: CellwiseDesign,
) -> None:
    if plt is None:
        return

    for title, q, cp, filename in (
        ("Nominal", None, 0.0, "46_recovery_nominal_S11_S21.png"),
        ("Q80/Cp40", 80.0, 40.0, "47_recovery_Q80Cp40_S11_S21.png"),
        ("Q60/Cp60", 60.0, 60.0, "48_recovery_Q60Cp60_S11_S21.png"),
    ):
        s11_b, s21_b = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, before, low, high, qind=q, cp_fF=cp
        )
        s11_a, s21_a = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, after, low, high, qind=q, cp_fF=cp
        )

        fig = plt.figure(figsize=(9.5, 5.6))
        plt.plot(f_ghz, db20(s21_b), label=f"S21 before {title}")
        plt.plot(f_ghz, db20(s21_a), label=f"S21 after {title}")
        plt.plot(f_ghz, db20(s11_a), label=f"S11 after {title}")
        plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
        plt.axhline(-50.0, linewidth=0.8)
        plt.xlabel("Frequency (GHz)")
        plt.ylabel("Magnitude (dB)")
        plt.title(f"3Rx4 Final Lower-Stopband Recovery - {title}")
        plt.ylim(-80, 2)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        fig.savefig(outdir/filename, dpi=220)
        plt.close(fig)



# =============================================================================
# 6M. LAST MICRO-TRIM: Q60 LOWER FAR-STOP TO >=50 dB
# =============================================================================

LAST_TARGET_DB = 50.0
LAST_WINDOWS = (0.0010, 0.0005)      # +/-0.10%, then +/-0.05%
LAST_MIN_STEP_REJ_DB = 1e-4

# Slightly relaxed only where needed, compared with the previous recovery stage.
LAST_NOM_RIPPLE_MAX_DB = 0.545
LAST_Q80_RIPPLE_MAX_DB = 0.685
LAST_Q60_RIPPLE_MAX_DB = 0.840
LAST_Q60_IL_MAX_DB = 1.505
LAST_NOM_BW_MIN_GHZ = 0.80
LAST_Q80_BW_MIN_GHZ = 0.80
LAST_Q60_BW_MIN_GHZ = 0.78
LAST_Q60_S11_MAX_DB = -7.8
LAST_TZ_TOL_GHZ = 0.025

# Only these microscopic degrees of freedom are allowed.
LAST_PARAMETER_ORDER = ("L3_nH", "L7a_nH", "L7b_nH", "L7c_nH")

# Revisit cells in the order that historically mattered most to robustness.
LAST_CELL_ORDER = (3, 0, 2, 1)  # Cell 4 -> 1 -> 3 -> 2

# NEW: after each cell-local pass, re-optimize the two GLOBAL matching inductors
# together.  Cell-by-cell asymmetry changes the optimum end matching, so L4/L6
# are no longer assumed to remain optimal at their pre-cellwise values.
GLOBAL_L4L6_COARSE_FRAC = 0.0010   # +/-0.10%
GLOBAL_L4L6_FINE_FRAC   = 0.00030  # +/-0.03% around coarse winner
GLOBAL_L4L6_NPTS        = 9
GLOBAL_REJ_DRIFT_MAX_DB = 0.020    # allow <=0.02 dB lower-stop drift to buy ripple
GLOBAL_REJ_ABS_FLOOR_DB = 49.85    # never undo the recovered stopband materially


def last_micro_guard(v: dict) -> bool:
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]

    return (
        n["passband_ripple_dB"] <= LAST_NOM_RIPPLE_MAX_DB
        and q80["passband_ripple_dB"] <= LAST_Q80_RIPPLE_MAX_DB
        and q60["passband_ripple_dB"] <= LAST_Q60_RIPPLE_MAX_DB
        and q60["minimum_IL_dB"] <= LAST_Q60_IL_MAX_DB
        and n["BW_3dB_GHz"] >= LAST_NOM_BW_MIN_GHZ
        and q80["BW_3dB_GHz"] >= LAST_Q80_BW_MIN_GHZ
        and q60["BW_3dB_GHz"] >= LAST_Q60_BW_MIN_GHZ
        and q60["worst_S11_dB"] <= LAST_Q60_S11_MAX_DB
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= LAST_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= LAST_TZ_TOL_GHZ

        # Preserve all other far-stop sides.
        and n["lower_stopband_min_rejection_dB"] >= 50.0
        and n["upper_stopband_min_rejection_dB"] >= 50.0
        and q80["lower_stopband_min_rejection_dB"] >= 50.0
        and q80["upper_stopband_min_rejection_dB"] >= 50.0
        and q60["upper_stopband_min_rejection_dB"] >= 50.0
    )


def last_micro_score(v: dict) -> float:
    """
    Used only as a tie-break once candidates have comparable lower-stop recovery.
    """
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        1.00*q60["passband_ripple_dB"]
        + 0.55*q60["minimum_IL_dB"]
        + 0.10*q80["passband_ripple_dB"]
        + 0.05*n["passband_ripple_dB"]
        + 0.03*max(0.0, q60["worst_S11_dB"] + 8.0)
    )


def _last_better(v_new: dict, v_old: dict) -> bool:
    rnew = v_new["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
    rold = v_old["Q60_Cp60"]["lower_stopband_min_rejection_dB"]

    old_met = rold >= LAST_TARGET_DB
    new_met = rnew >= LAST_TARGET_DB

    if old_met:
        if not new_met:
            return False
        return last_micro_score(v_new) < last_micro_score(v_old) - 1e-10

    if new_met:
        return True

    # While still below 50 dB, prioritize rejection recovery.
    if rnew <= rold + LAST_MIN_STEP_REJ_DB:
        return False

    # Permit only tiny passband-score drift before the target is reached.
    return last_micro_score(v_new) <= last_micro_score(v_old) + 0.004


def _last_scan_parameter(
    base: CellwiseDesign,
    cell_index: int,
    parameter: str,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Scan exactly one parameter of one cell.
    """
    names_all = ["L3_nH", "L5_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"]
    pidx = names_all.index(parameter)

    c0 = base.cells[cell_index]
    x0 = _cell_vector(c0)
    center = x0[pidx]
    lo_abs, hi_abs = _CELLWISE_BOUNDS[parameter]

    # Dense enough to resolve a ~0.15 dB rejection deficit without large movement.
    vals = np.linspace(
        max(lo_abs, center*(1-frac)),
        min(hi_abs, center*(1+frac)),
        61,
    )

    vbase = verify_cellwise_extended(base, low, high, f_ghz)
    best_d, best_v = base, vbase

    for val in vals:
        x = x0.copy()
        x[pidx] = float(val)
        cand = replace_cell(base, cell_index, _cell_from_vector(x))
        vv = verify_cellwise_extended(cand, low, high, f_ghz)

        if not last_micro_guard(vv):
            continue

        if _last_better(vv, best_v):
            best_d, best_v = cand, vv

            # Exact purpose of this stage: stop as soon as the target is crossed.
            if vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB:
                break

    return best_d, best_v


def _global_l4l6_passband_score(v: dict) -> float:
    """Passband-first score used only for the inter-cell GLOBAL L4/L6 retune."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        4.00*q60["passband_ripple_dB"]
        + 2.00*n["passband_ripple_dB"]
        + 0.50*q60["minimum_IL_dB"]
        + 0.20*q80["passband_ripple_dB"]
        + 0.05*max(0.0, q60["worst_S11_dB"] + 8.0)
    )


def _joint_l4l6_micro_retune(
    base: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Joint 2-D GLOBAL L4/L6 micro-retune after one cell has been processed.

    Passband ripple is the primary objective.  The Q60 lower far-stop side may
    move by at most GLOBAL_REJ_DRIFT_MAX_DB, and never below the absolute floor.
    All original LAST micro guardrails remain active.
    """
    vbase = verify_cellwise_extended(base, low, high, f_ghz)
    rbase = vbase["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
    rej_floor = max(GLOBAL_REJ_ABS_FLOOR_DB, rbase - GLOBAL_REJ_DRIFT_MAX_DB)

    best_d, best_v = base, vbase
    best_score = _global_l4l6_passband_score(vbase)

    def run_grid(center: CellwiseDesign, frac: float):
        nonlocal best_d, best_v, best_score
        l4_vals = np.linspace(center.L4_nH*(1-frac), center.L4_nH*(1+frac), GLOBAL_L4L6_NPTS)
        l6_vals = np.linspace(center.L6_nH*(1-frac), center.L6_nH*(1+frac), GLOBAL_L4L6_NPTS)

        for l4 in l4_vals:
            for l6 in l6_vals:
                cand = replace_terminals(base, L4_nH=float(l4), L6_nH=float(l6))
                vv = verify_cellwise_extended(cand, low, high, f_ghz)
                if not last_micro_guard(vv):
                    continue
                if vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"] < rej_floor:
                    continue

                sc = _global_l4l6_passband_score(vv)
                if sc < best_score - 1e-10:
                    best_d, best_v, best_score = cand, vv, sc

    # Coarse 2-D search, then a narrower search around its winner.
    run_grid(base, GLOBAL_L4L6_COARSE_FRAC)
    coarse = best_d
    run_grid(coarse, GLOBAL_L4L6_FINE_FRAC)

    improved = best_score < _global_l4l6_passband_score(vbase) - 1e-10
    return best_d, best_v, improved, rej_floor


def final_last_micro_trim(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Final microscopic recovery.

    Pass 1: +/-0.10%
    Pass 2: +/-0.05%

    For each pass:
      Cell 4 -> Cell 1 -> Cell 3 -> Cell 2

    Within each cell:
      L3 -> L7a -> L7b -> L7c
      -> GLOBAL joint L4/L6 2-D micro-retune

    Cell-local parameters are still changed one at a time; L4/L6 are then
    optimized jointly because they are global matching elements.
    Stop immediately once Q60/Cp60 lower far-stop rejection >=50 dB.
    """
    current = start
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    history = []

    print("\n" + "="*78)
    print("LAST MICRO-TRIM + INTER-CELL GLOBAL L4/L6 RETUNE")
    print("="*78)
    print(
        f"Start lower far-rej="
        f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB | "
        f"Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
        f"IL={vcur['Q60_Cp60']['minimum_IL_dB']:.6f} dB"
    )

    if vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB:
        return current, vcur, history, True

    for frac in LAST_WINDOWS:
        print(f"\nMicro window +/-{100*frac:.3f}%")

        for cell_index in LAST_CELL_ORDER:
            for parameter in LAST_PARAMETER_ORDER:
                vb = vcur
                rb = vb["Q60_Cp60"]["lower_stopband_min_rejection_dB"]

                trial, vt = _last_scan_parameter(
                    current, cell_index, parameter, frac,
                    low, high, f_ghz
                )

                rt = vt["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
                accept = last_micro_guard(vt) and _last_better(vt, vb)

                if accept:
                    current, vcur = trial, vt
                    print(
                        f"Cell {cell_index+1} {parameter}: ACCEPT | "
                        f"rej {rb:.6f} -> {rt:.6f} dB | "
                        f"Q60 ripple={vt['Q60_Cp60']['passband_ripple_dB']:.6f} | "
                        f"IL={vt['Q60_Cp60']['minimum_IL_dB']:.6f} | "
                        f"nom={vt['nominal']['passband_ripple_dB']:.6f}"
                    )
                else:
                    print(
                        f"Cell {cell_index+1} {parameter}: REJECT | "
                        f"rej remains {rb:.6f} dB"
                    )

                history.append({
                    "window_percent": 100*frac,
                    "cell": cell_index+1,
                    "parameter": parameter,
                    "accepted": bool(accept),
                    "Q60_lower_far_rej_before_dB": rb,
                    "Q60_lower_far_rej_after_dB":
                        vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                    "Q60_ripple_after_dB":
                        vcur["Q60_Cp60"]["passband_ripple_dB"],
                    "Q60_IL_after_dB":
                        vcur["Q60_Cp60"]["minimum_IL_dB"],
                    "nominal_ripple_after_dB":
                        vcur["nominal"]["passband_ripple_dB"],
                    "design_after": current.to_dict(),
                })

                if (
                    vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
                    >= LAST_TARGET_DB
                ):
                    print(
                        f"TARGET REACHED: lower far-stop rejection="
                        f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB"
                    )
                    return current, vcur, history, True

            # NEW: after this cell's local coordinates, jointly re-match GLOBAL L4/L6.
            vb_global = vcur
            rb_global = vb_global["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
            sd_global = _global_l4l6_passband_score(vb_global)
            trial_g, vt_g, improved_g, rej_floor_g = _joint_l4l6_micro_retune(
                current, low, high, f_ghz
            )
            if improved_g:
                current, vcur = trial_g, vt_g
                print(
                    f"Cell {cell_index+1} GLOBAL L4/L6: ACCEPT | "
                    f"L4={current.L4_nH:.9f} nH | L6={current.L6_nH:.9f} nH | "
                    f"Q60 ripple {vb_global['Q60_Cp60']['passband_ripple_dB']:.6f} -> "
                    f"{vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                    f"nom {vb_global['nominal']['passband_ripple_dB']:.6f} -> "
                    f"{vcur['nominal']['passband_ripple_dB']:.6f} dB | "
                    f"rej {rb_global:.6f} -> "
                    f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB"
                )
            else:
                print(
                    f"Cell {cell_index+1} GLOBAL L4/L6: REJECT | "
                    f"L4/L6 remain {current.L4_nH:.9f}/{current.L6_nH:.9f} nH"
                )

            history.append({
                "window_percent": 100*frac,
                "cell": cell_index+1,
                "parameter": "GLOBAL_L4_L6",
                "accepted": bool(improved_g),
                "L4_nH_after": current.L4_nH,
                "L6_nH_after": current.L6_nH,
                "Q60_lower_far_rej_before_dB": rb_global,
                "Q60_lower_far_rej_after_dB":
                    vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "Q60_ripple_after_dB": vcur["Q60_Cp60"]["passband_ripple_dB"],
                "Q60_IL_after_dB": vcur["Q60_Cp60"]["minimum_IL_dB"],
                "nominal_ripple_after_dB": vcur["nominal"]["passband_ripple_dB"],
                "global_rej_floor_dB": rej_floor_g,
                "global_score_before": sd_global,
                "global_score_after": _global_l4l6_passband_score(vcur),
                "design_after": current.to_dict(),
            })

            if vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB:
                print(
                    f"TARGET REACHED AFTER GLOBAL L4/L6: lower far-stop rejection="
                    f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB"
                )
                return current, vcur, history, True

    ok = vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB
    return current, vcur, history, ok



# =============================================================================
# 6N. ULTRA-FINE GLOBAL L4/L6 CLOSURE (FIX ALL CELL PARAMETERS)
# =============================================================================

ULTRA_L4L6_WINDOWS = (0.00020, 0.00010, 0.00005)  # +/-0.020%, 0.010%, 0.005%
ULTRA_L4L6_NPTS = 13
ULTRA_Q60_RIPPLE_MAX_DB = 0.815
ULTRA_NOM_RIPPLE_MAX_DB = 0.540
ULTRA_Q80_RIPPLE_MAX_DB = 0.660
ULTRA_Q60_BW_MIN_GHZ = 0.810
ULTRA_NOM_BW_MIN_GHZ = 0.830
ULTRA_Q80_BW_MIN_GHZ = 0.815
ULTRA_Q60_S11_MAX_DB = -8.0
ULTRA_IL_DRIFT_MAX_DB = 0.010


def _ultra_l4l6_guard(v: dict, base_il: float) -> bool:
    """Hard protection for the final rejection-closure search."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        q60["passband_ripple_dB"] <= ULTRA_Q60_RIPPLE_MAX_DB
        and n["passband_ripple_dB"] <= ULTRA_NOM_RIPPLE_MAX_DB
        and q80["passband_ripple_dB"] <= ULTRA_Q80_RIPPLE_MAX_DB
        and q60["BW_3dB_GHz"] >= ULTRA_Q60_BW_MIN_GHZ
        and n["BW_3dB_GHz"] >= ULTRA_NOM_BW_MIN_GHZ
        and q80["BW_3dB_GHz"] >= ULTRA_Q80_BW_MIN_GHZ
        and q60["minimum_IL_dB"] <= base_il + ULTRA_IL_DRIFT_MAX_DB
        and q60["worst_S11_dB"] <= ULTRA_Q60_S11_MAX_DB
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= LAST_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= LAST_TZ_TOL_GHZ
        and n["lower_stopband_min_rejection_dB"] >= 50.0
        and n["upper_stopband_min_rejection_dB"] >= 50.0
        and q80["lower_stopband_min_rejection_dB"] >= 50.0
        and q80["upper_stopband_min_rejection_dB"] >= 50.0
        and q60["upper_stopband_min_rejection_dB"] >= 50.0
    )


def _ultra_post_target_score(v: dict) -> float:
    """Once 50 dB is crossed, prefer the cleanest passband among target-meeting points."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        5.0*q60["passband_ripple_dB"]
        + 2.0*n["passband_ripple_dB"]
        + 0.5*q80["passband_ripple_dB"]
        + 0.25*q60["minimum_IL_dB"]
    )


def ultrafine_global_l4l6_closure(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Freeze every cell-local parameter and search ONLY global L4/L6.

    Three nested 2-D grids are used: +/-0.020%, +/-0.010%, +/-0.005%.
    Before 50 dB is reached, lower Q60 far-stop rejection is the primary
    objective.  After the target is reached, the best target-meeting point is
    selected by passband quality under strict hard guardrails.
    """
    current = start
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    base_il = vcur["Q60_Cp60"]["minimum_IL_dB"]
    rows = []

    print("\n" + "="*78)
    print("ULTRA-FINE GLOBAL L4/L6 CLOSURE — ALL CELL PARAMETERS FIXED")
    print("="*78)
    print(
        f"Start: L4={current.L4_nH:.9f} nH | L6={current.L6_nH:.9f} nH | "
        f"Q60 lower far-rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB | "
        f"ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
        f"nom={vcur['nominal']['passband_ripple_dB']:.6f} dB"
    )

    for level, frac in enumerate(ULTRA_L4L6_WINDOWS, start=1):
        center = current
        l4_vals = np.linspace(center.L4_nH*(1-frac), center.L4_nH*(1+frac), ULTRA_L4L6_NPTS)
        l6_vals = np.linspace(center.L6_nH*(1-frac), center.L6_nH*(1+frac), ULTRA_L4L6_NPTS)

        feasible = []
        for l4 in l4_vals:
            for l6 in l6_vals:
                cand = replace_terminals(start, L4_nH=float(l4), L6_nH=float(l6))
                vv = verify_cellwise_extended(cand, low, high, f_ghz)
                if not _ultra_l4l6_guard(vv, base_il):
                    continue
                feasible.append((cand, vv))
                rows.append({
                    "level": level,
                    "window_percent": 100*frac,
                    "L4_nH": float(l4),
                    "L6_nH": float(l6),
                    "Q60_lower_far_rej_dB": vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                    "Q60_ripple_dB": vv["Q60_Cp60"]["passband_ripple_dB"],
                    "Q60_IL_dB": vv["Q60_Cp60"]["minimum_IL_dB"],
                    "Q60_BW_GHz": vv["Q60_Cp60"]["BW_3dB_GHz"],
                    "nominal_ripple_dB": vv["nominal"]["passband_ripple_dB"],
                    "Q80_ripple_dB": vv["Q80_Cp40"]["passband_ripple_dB"],
                })

        if not feasible:
            print(f"Level {level} +/-{100*frac:.3f}%: no feasible candidate")
            continue

        target_points = [x for x in feasible if x[1]["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB]
        if target_points:
            best_d, best_v = min(target_points, key=lambda x: _ultra_post_target_score(x[1]))
        else:
            # Rejection first; passband score only breaks numerically close ties.
            best_d, best_v = max(
                feasible,
                key=lambda x: (
                    x[1]["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                    -_ultra_post_target_score(x[1]),
                ),
            )

        old_r = vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
        new_r = best_v["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
        # Never move backward before the 50-dB target.  Once met, score may choose
        # a slightly lower-rejection point, but it must still remain >=50 dB.
        if old_r < LAST_TARGET_DB and new_r < old_r - 1e-12:
            print(f"Level {level} +/-{100*frac:.3f}%: REJECT (would reduce rejection)")
            continue

        current, vcur = best_d, best_v
        print(
            f"Level {level} +/-{100*frac:.3f}%: ACCEPT | "
            f"L4={current.L4_nH:.9f} | L6={current.L6_nH:.9f} | "
            f"rej {old_r:.6f} -> {new_r:.6f} dB | "
            f"Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} | "
            f"nom={vcur['nominal']['passband_ripple_dB']:.6f}"
        )

    ok = vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB
    return current, vcur, pd.DataFrame(rows), ok



# =============================================================================
# 6O. ULTRA-MICRO CELL L3 + GLOBAL L4/L6 COMPENSATION
# =============================================================================

L3_ULTRA_WINDOWS = (0.00020, 0.00010)   # +/-0.020%, +/-0.010%
L3_ULTRA_NPTS = 13
L3_ULTRA_CELL_ORDER = (0, 1, 2, 3)      # Cell 1 -> 2 -> 3 -> 4
L3_COMP_NPTS = 11
L3_Q60_RIPPLE_MAX_DB = 0.812
L3_NOM_RIPPLE_MAX_DB = 0.540
L3_Q80_RIPPLE_MAX_DB = 0.660
L3_Q60_BW_MIN_GHZ = 0.810
L3_NOM_BW_MIN_GHZ = 0.830
L3_Q80_BW_MIN_GHZ = 0.815
L3_Q60_S11_MAX_DB = -8.0
L3_Q60_IL_DRIFT_MAX_DB = 0.012


def _replace_cell_l3(d: CellwiseDesign, cell_index: int, new_l3_nH: float) -> CellwiseDesign:
    """Replace only one cell's L3; every other cell-local parameter remains frozen."""
    old = d.cells[cell_index]
    new = CellParams(
        L3_nH=float(new_l3_nH),
        L5_nH=old.L5_nH,
        C1_pF=old.C1_pF,
        L7a_nH=old.L7a_nH,
        L7b_nH=old.L7b_nH,
        L7c_nH=old.L7c_nH,
    )
    return replace_cell(d, cell_index, new)


def _l3_ultra_guard(v: dict, base_il: float) -> bool:
    """Hard protection for the last 50-dB closure attempt."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    return (
        q60["passband_ripple_dB"] <= L3_Q60_RIPPLE_MAX_DB
        and n["passband_ripple_dB"] <= L3_NOM_RIPPLE_MAX_DB
        and q80["passband_ripple_dB"] <= L3_Q80_RIPPLE_MAX_DB
        and q60["BW_3dB_GHz"] >= L3_Q60_BW_MIN_GHZ
        and n["BW_3dB_GHz"] >= L3_NOM_BW_MIN_GHZ
        and q80["BW_3dB_GHz"] >= L3_Q80_BW_MIN_GHZ
        and q60["minimum_IL_dB"] <= base_il + L3_Q60_IL_DRIFT_MAX_DB
        and q60["worst_S11_dB"] <= L3_Q60_S11_MAX_DB
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= LAST_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= LAST_TZ_TOL_GHZ
        and n["lower_stopband_min_rejection_dB"] >= 50.0
        and n["upper_stopband_min_rejection_dB"] >= 50.0
        and q80["lower_stopband_min_rejection_dB"] >= 50.0
        and q80["upper_stopband_min_rejection_dB"] >= 50.0
        and q60["upper_stopband_min_rejection_dB"] >= 50.0
    )


def _l3_closure_rank(v: dict):
    """Rejection-first before 50 dB; passband quality is the tie breaker."""
    q60 = v["Q60_Cp60"]
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    return (
        q60["lower_stopband_min_rejection_dB"],
        -q60["passband_ripple_dB"],
        -n["passband_ripple_dB"],
        -q80["passband_ripple_dB"],
        -q60["minimum_IL_dB"],
    )


def _l3_post_target_score(v: dict) -> float:
    """After 50 dB is crossed, retain margin while preferring a clean passband."""
    q60 = v["Q60_Cp60"]
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    margin = q60["lower_stopband_min_rejection_dB"] - LAST_TARGET_DB
    return (
        6.0*q60["passband_ripple_dB"]
        + 2.0*n["passband_ripple_dB"]
        + 0.75*q80["passband_ripple_dB"]
        + 0.30*q60["minimum_IL_dB"]
        - 0.20*min(max(margin, 0.0), 0.10)
    )


def _choose_l3_candidate(feasible, current_rej: float):
    if not feasible:
        return None
    target_points = [x for x in feasible
                     if x[1]["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB]
    if target_points:
        return min(target_points, key=lambda x: _l3_post_target_score(x[1]))
    best = max(feasible, key=lambda x: _l3_closure_rank(x[1]))
    if best[1]["Q60_Cp60"]["lower_stopband_min_rejection_dB"] < current_rej - 1e-12:
        return None
    return best


def _l4l6_compensate_after_l3(
    base: CellwiseDesign,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    base_il: float,
):
    """Tiny joint L4/L6 compensation around the newly perturbed cell state."""
    v0 = verify_cellwise_extended(base, low, high, f_ghz)
    old_rej = v0["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
    l4_vals = np.linspace(base.L4_nH*(1-frac), base.L4_nH*(1+frac), L3_COMP_NPTS)
    l6_vals = np.linspace(base.L6_nH*(1-frac), base.L6_nH*(1+frac), L3_COMP_NPTS)
    feasible = []
    rows = []
    for l4 in l4_vals:
        for l6 in l6_vals:
            cand = replace_terminals(base, L4_nH=float(l4), L6_nH=float(l6))
            vv = verify_cellwise_extended(cand, low, high, f_ghz)
            if not _l3_ultra_guard(vv, base_il):
                continue
            feasible.append((cand, vv))
            rows.append({
                "L4_nH": float(l4),
                "L6_nH": float(l6),
                "Q60_lower_far_rej_dB": vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "Q60_ripple_dB": vv["Q60_Cp60"]["passband_ripple_dB"],
                "Q60_IL_dB": vv["Q60_Cp60"]["minimum_IL_dB"],
                "nominal_ripple_dB": vv["nominal"]["passband_ripple_dB"],
            })
    choice = _choose_l3_candidate(feasible, old_rej)
    if choice is None:
        return base, v0, rows, False
    cand, vv = choice
    changed = (abs(cand.L4_nH-base.L4_nH) > 1e-15 or abs(cand.L6_nH-base.L6_nH) > 1e-15)
    return cand, vv, rows, changed


def ultramicro_l3_with_l4l6_compensation(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Final closure attempt from the ultra-fine L4/L6 checkpoint.

    Only one cell L3 is perturbed at a time. After each accepted L3 move,
    perform a tiny 2-D global L4/L6 compensation. All L5/C1/L7 values remain fixed.
    Two cyclic windows are used: +/-0.020%, then +/-0.010%.
    """
    current = start
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    base_il = vcur["Q60_Cp60"]["minimum_IL_dB"]
    history = []
    surface_rows = []

    print("\n" + "="*78)
    print("ULTRA-MICRO CELL L3 + GLOBAL L4/L6 COMPENSATION")
    print("="*78)
    print(
        f"Start: rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB | "
        f"Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
        f"nom={vcur['nominal']['passband_ripple_dB']:.6f} dB | "
        f"L4={current.L4_nH:.9f} | L6={current.L6_nH:.9f}"
    )

    for cycle, frac in enumerate(L3_ULTRA_WINDOWS, start=1):
        print(f"\nCycle {cycle}: L3 +/-{100*frac:.3f}% with L4/L6 compensation +/-{100*frac:.3f}%")
        for ci in L3_ULTRA_CELL_ORDER:
            old = current
            oldv = vcur
            old_rej = oldv["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
            center = current.cells[ci].L3_nH
            lo_bound, hi_bound = _CELLWISE_BOUNDS["L3_nH"]
            vals = np.linspace(
                max(lo_bound, center*(1-frac)),
                min(hi_bound, center*(1+frac)),
                L3_ULTRA_NPTS,
            )
            feasible = []
            for val in vals:
                cand = _replace_cell_l3(current, ci, float(val))
                vv = verify_cellwise_extended(cand, low, high, f_ghz)
                surface_rows.append({
                    "cycle": cycle, "stage": "L3", "cell": ci+1,
                    "window_percent": 100*frac, "L3_nH": float(val),
                    "L4_nH": current.L4_nH, "L6_nH": current.L6_nH,
                    "feasible": bool(_l3_ultra_guard(vv, base_il)),
                    "Q60_lower_far_rej_dB": vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                    "Q60_ripple_dB": vv["Q60_Cp60"]["passband_ripple_dB"],
                    "Q60_IL_dB": vv["Q60_Cp60"]["minimum_IL_dB"],
                    "nominal_ripple_dB": vv["nominal"]["passband_ripple_dB"],
                })
                if _l3_ultra_guard(vv, base_il):
                    feasible.append((cand, vv))

            choice = _choose_l3_candidate(feasible, old_rej)
            if choice is None:
                print(f"Cell {ci+1} L3: REJECT | rej remains {old_rej:.6f} dB")
                history.append({"cycle": cycle, "cell": ci+1, "stage": "L3", "accepted": False})
                continue

            trial, vtrial = choice
            new_rej = vtrial["Q60_Cp60"]["lower_stopband_min_rejection_dB"]
            changed = abs(trial.cells[ci].L3_nH - current.cells[ci].L3_nH) > 1e-15
            if changed:
                current, vcur = trial, vtrial
                print(
                    f"Cell {ci+1} L3: ACCEPT | {old.cells[ci].L3_nH:.9f} -> "
                    f"{current.cells[ci].L3_nH:.9f} nH | rej {old_rej:.6f} -> {new_rej:.6f} dB | "
                    f"Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f}"
                )
            else:
                print(f"Cell {ci+1} L3: HOLD | center remains best")

            history.append({
                "cycle": cycle, "cell": ci+1, "stage": "L3",
                "accepted": bool(changed),
                "L3_before_nH": old.cells[ci].L3_nH,
                "L3_after_nH": current.cells[ci].L3_nH,
                "rej_before_dB": old_rej,
                "rej_after_dB": vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "Q60_ripple_after_dB": vcur["Q60_Cp60"]["passband_ripple_dB"],
            })

            # Always test global compensation after the cell checkpoint, even if L3 stayed at center.
            precomp = current
            precomp_v = vcur
            comp, comp_v, comp_rows, comp_changed = _l4l6_compensate_after_l3(
                current, frac, low, high, f_ghz, base_il
            )
            for rr in comp_rows:
                rr.update({"cycle": cycle, "stage": "L4L6_comp", "cell": ci+1,
                           "window_percent": 100*frac, "L3_nH": current.cells[ci].L3_nH,
                           "feasible": True})
                surface_rows.append(rr)
            if comp_changed:
                current, vcur = comp, comp_v
                print(
                    f"Cell {ci+1} GLOBAL L4/L6: ACCEPT | "
                    f"L4={current.L4_nH:.9f}, L6={current.L6_nH:.9f} | "
                    f"rej {precomp_v['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} -> "
                    f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB | "
                    f"Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f}"
                )
            else:
                print(f"Cell {ci+1} GLOBAL L4/L6: REJECT/HOLD")
            history.append({
                "cycle": cycle, "cell": ci+1, "stage": "L4L6_comp",
                "accepted": bool(comp_changed),
                "L4_before_nH": precomp.L4_nH, "L4_after_nH": current.L4_nH,
                "L6_before_nH": precomp.L6_nH, "L6_after_nH": current.L6_nH,
                "rej_after_dB": vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "Q60_ripple_after_dB": vcur["Q60_Cp60"]["passband_ripple_dB"],
            })

        if vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB:
            print(
                f"TARGET >=50 dB REACHED after cycle {cycle}: "
                f"{vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB"
            )
            break

    ok = vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"] >= LAST_TARGET_DB
    return current, vcur, history, pd.DataFrame(surface_rows), ok


# =============================================================================
# 6P. RIPPLE-FIRST RELAXED-REJECTION BRANCH (Q60 ripple target <=0.80 dB)
# =============================================================================

R45_REJECTION_MIN_DB = 45.0
R45_Q60_RIPPLE_TARGET_DB = 0.750
R45_NOM_RIPPLE_MAX_DB = 0.540
R45_Q80_RIPPLE_MAX_DB = 0.650
R45_Q60_BW_MIN_GHZ = 0.800
R45_NOM_BW_MIN_GHZ = 0.830
R45_Q80_BW_MIN_GHZ = 0.815
R45_Q60_S11_MAX_DB = -8.0
R45_Q60_IL_DRIFT_MAX_DB = 0.050
R45_TZ_TOL_GHZ = 0.025
R45_WINDOWS = (0.0030, 0.0015, 0.0005)   # +/-0.30%, +/-0.15%, +/-0.05%
R45_CELL_ORDER = (3, 0, 2, 1)            # Cell 4 -> 1 -> 3 -> 2
R45_PARAMETER_ORDER = ("L3_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH")
R45_PARAM_NPTS = 9
R45_TERMINAL_NPTS = 9


def _r45_guard(v: dict, branch_start_il: float) -> bool:
    """Hard guards for the >45-dB ripple-optimized branch."""
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    q60 = v["Q60_Cp60"]
    scenarios = (n, q80, q60)
    return (
        n["passband_ripple_dB"] <= R45_NOM_RIPPLE_MAX_DB
        and q80["passband_ripple_dB"] <= R45_Q80_RIPPLE_MAX_DB
        and q60["BW_3dB_GHz"] >= R45_Q60_BW_MIN_GHZ
        and n["BW_3dB_GHz"] >= R45_NOM_BW_MIN_GHZ
        and q80["BW_3dB_GHz"] >= R45_Q80_BW_MIN_GHZ
        and q60["minimum_IL_dB"] <= branch_start_il + R45_Q60_IL_DRIFT_MAX_DB
        and q60["worst_S11_dB"] <= R45_Q60_S11_MAX_DB
        and abs(q60["TZL"]["GHz"] - TZ_TARGETS_GHZ[0]) <= R45_TZ_TOL_GHZ
        and abs(q60["TZU"]["GHz"] - TZ_TARGETS_GHZ[1]) <= R45_TZ_TOL_GHZ
        and all(m["lower_stopband_min_rejection_dB"] >= R45_REJECTION_MIN_DB for m in scenarios)
        and all(m["upper_stopband_min_rejection_dB"] >= R45_REJECTION_MIN_DB for m in scenarios)
    )


def _r45_rank(v: dict):
    """Ripple first; rejection is only a guardrail once it is above 45 dB."""
    q60 = v["Q60_Cp60"]
    n = v["nominal"]
    q80 = v["Q80_Cp40"]
    return (
        q60["passband_ripple_dB"],
        n["passband_ripple_dB"],
        q80["passband_ripple_dB"],
        q60["minimum_IL_dB"],
        -q60["lower_stopband_min_rejection_dB"],
        -q60["BW_3dB_GHz"],
    )


def _replace_cell_parameter(d: CellwiseDesign, cell_index: int, name: str, value: float) -> CellwiseDesign:
    c = d.cells[cell_index]
    vals = {
        "L3_nH": c.L3_nH,
        "L5_nH": c.L5_nH,
        "C1_pF": c.C1_pF,
        "L7a_nH": c.L7a_nH,
        "L7b_nH": c.L7b_nH,
        "L7c_nH": c.L7c_nH,
    }
    vals[name] = float(value)
    return replace_cell(d, cell_index, CellParams(**vals))


def _r45_terminal_search(
    current: CellwiseDesign,
    frac: float,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    branch_start_il: float,
    cycle: int,
    tag: str,
):
    """Joint L4/L6 search, accepting only a strict Q60-ripple improvement."""
    v0 = verify_cellwise_extended(current, low, high, f_ghz)
    r0 = v0["Q60_Cp60"]["passband_ripple_dB"]
    l4vals = np.linspace(current.L4_nH*(1-frac), current.L4_nH*(1+frac), R45_TERMINAL_NPTS)
    l6vals = np.linspace(current.L6_nH*(1-frac), current.L6_nH*(1+frac), R45_TERMINAL_NPTS)
    best = None
    rows = []
    for l4 in l4vals:
        for l6 in l6vals:
            cand = replace_terminals(current, L4_nH=float(l4), L6_nH=float(l6))
            vv = verify_cellwise_extended(cand, low, high, f_ghz)
            feasible = _r45_guard(vv, branch_start_il)
            rows.append({
                "cycle": cycle, "stage": tag, "cell": 0, "parameter": "L4_L6",
                "window_percent": 100*frac, "L4_nH": float(l4), "L6_nH": float(l6),
                "feasible": bool(feasible),
                "Q60_ripple_dB": vv["Q60_Cp60"]["passband_ripple_dB"],
                "Q60_IL_dB": vv["Q60_Cp60"]["minimum_IL_dB"],
                "Q60_lower_rej_dB": vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                "Q60_upper_rej_dB": vv["Q60_Cp60"]["upper_stopband_min_rejection_dB"],
                "nominal_ripple_dB": vv["nominal"]["passband_ripple_dB"],
                "Q80_ripple_dB": vv["Q80_Cp40"]["passband_ripple_dB"],
            })
            if not feasible or vv["Q60_Cp60"]["passband_ripple_dB"] >= r0 - 1e-9:
                continue
            if best is None or _r45_rank(vv) < _r45_rank(best[1]):
                best = (cand, vv)
    if best is None:
        return current, v0, rows, False
    return best[0], best[1], rows, True


def ripple_optimized_45db_branch(
    start: CellwiseDesign,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
):
    """
    Independent branch from the preserved >=50-dB FINAL checkpoint.

    Objective: minimize Q60/Cp60 passband ripple.
    Final success requires nominal ripple <0.54 dB, Q80/Cp40 <0.65 dB, Q60/Cp60 <0.75 dB, and all far-stop rejection >45 dB.
    Rejection above 45 dB is a guardrail, not an optimization reward.
    L5 remains frozen; L4/L6, cell L3, C1 and segmented L7 are reopened locally.
    """
    current = start
    vcur = verify_cellwise_extended(current, low, high, f_ghz)
    branch_start_il = vcur["Q60_Cp60"]["minimum_IL_dB"]
    history = []
    surface = []

    print("\n" + "="*78)
    print("RIPPLE-FIRST RELAXED-REJECTION BRANCH — FAR-STOP >=45 dB")
    print("="*78)
    print(
        f"Start: Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
        f"lower rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.6f} dB | "
        f"IL={vcur['Q60_Cp60']['minimum_IL_dB']:.6f} dB"
    )

    for cycle, frac in enumerate(R45_WINDOWS, start=1):
        print(f"\nRipple cycle {cycle}: local window +/-{100*frac:.3f}%")

        before = current
        before_v = vcur
        current, vcur, rr, accepted = _r45_terminal_search(
            current, frac, low, high, f_ghz, branch_start_il, cycle, "terminal_pre"
        )
        surface.extend(rr)
        if accepted:
            print(
                f"GLOBAL L4/L6: ACCEPT | ripple "
                f"{before_v['Q60_Cp60']['passband_ripple_dB']:.6f} -> "
                f"{vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                f"rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.3f} dB"
            )
        else:
            print("GLOBAL L4/L6: HOLD")
        history.append({"cycle": cycle, "stage": "terminal_pre", "accepted": bool(accepted),
                        "Q60_ripple_dB": vcur["Q60_Cp60"]["passband_ripple_dB"],
                        "Q60_lower_rej_dB": vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"]})

        for ci in R45_CELL_ORDER:
            for par in R45_PARAMETER_ORDER:
                c = current.cells[ci]
                center = getattr(c, par)
                lo_abs, hi_abs = _CELLWISE_BOUNDS[par]
                vals = np.linspace(max(lo_abs, center*(1-frac)), min(hi_abs, center*(1+frac)), R45_PARAM_NPTS)
                old_v = vcur
                old_r = old_v["Q60_Cp60"]["passband_ripple_dB"]
                best = None
                for val in vals:
                    cand = _replace_cell_parameter(current, ci, par, float(val))
                    vv = verify_cellwise_extended(cand, low, high, f_ghz)
                    feasible = _r45_guard(vv, branch_start_il)
                    surface.append({
                        "cycle": cycle, "stage": "cell", "cell": ci+1, "parameter": par,
                        "window_percent": 100*frac, "value": float(val),
                        "L4_nH": current.L4_nH, "L6_nH": current.L6_nH,
                        "feasible": bool(feasible),
                        "Q60_ripple_dB": vv["Q60_Cp60"]["passband_ripple_dB"],
                        "Q60_IL_dB": vv["Q60_Cp60"]["minimum_IL_dB"],
                        "Q60_lower_rej_dB": vv["Q60_Cp60"]["lower_stopband_min_rejection_dB"],
                        "Q60_upper_rej_dB": vv["Q60_Cp60"]["upper_stopband_min_rejection_dB"],
                        "nominal_ripple_dB": vv["nominal"]["passband_ripple_dB"],
                        "Q80_ripple_dB": vv["Q80_Cp40"]["passband_ripple_dB"],
                    })
                    if not feasible or vv["Q60_Cp60"]["passband_ripple_dB"] >= old_r - 1e-9:
                        continue
                    if best is None or _r45_rank(vv) < _r45_rank(best[1]):
                        best = (cand, vv)
                if best is not None:
                    oldval = center
                    current, vcur = best
                    print(
                        f"Cell {ci+1} {par}: ACCEPT | {oldval:.9f} -> "
                        f"{getattr(current.cells[ci], par):.9f} | Q60 ripple "
                        f"{old_r:.6f} -> {vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                        f"rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.3f} dB"
                    )
                    history.append({"cycle": cycle, "stage": "cell", "cell": ci+1,
                                    "parameter": par, "accepted": True,
                                    "Q60_ripple_dB": vcur["Q60_Cp60"]["passband_ripple_dB"],
                                    "Q60_lower_rej_dB": vcur["Q60_Cp60"]["lower_stopband_min_rejection_dB"]})

            # Re-match globally after each completed cell.
            pre_v = vcur
            current2, v2, rr, accepted = _r45_terminal_search(
                current, frac, low, high, f_ghz, branch_start_il, cycle, f"terminal_after_cell{ci+1}"
            )
            surface.extend(rr)
            if accepted:
                current, vcur = current2, v2
                print(
                    f"Cell {ci+1} GLOBAL L4/L6: ACCEPT | Q60 ripple "
                    f"{pre_v['Q60_Cp60']['passband_ripple_dB']:.6f} -> "
                    f"{vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
                    f"rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.3f} dB"
                )

        print(
            f"Cycle {cycle} end: Q60 ripple={vcur['Q60_Cp60']['passband_ripple_dB']:.6f} dB | "
            f"lower rej={vcur['Q60_Cp60']['lower_stopband_min_rejection_dB']:.3f} dB | "
            f"nom={vcur['nominal']['passband_ripple_dB']:.6f} dB"
        )

    success = (
        vcur["nominal"]["passband_ripple_dB"] < R45_NOM_RIPPLE_MAX_DB
        and vcur["Q80_Cp40"]["passband_ripple_dB"] < R45_Q80_RIPPLE_MAX_DB
        and vcur["Q60_Cp60"]["passband_ripple_dB"] < R45_Q60_RIPPLE_TARGET_DB
        and all(
            vcur[name][side] > R45_REJECTION_MIN_DB
            for name in ("nominal", "Q80_Cp40", "Q60_Cp60")
            for side in ("lower_stopband_min_rejection_dB", "upper_stopband_min_rejection_dB")
        )
        and _r45_guard(vcur, branch_start_il)
    )
    return current, vcur, history, pd.DataFrame(surface), bool(success)


def plot_last_micro_trim(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    before: CellwiseDesign,
    after: CellwiseDesign,
) -> None:
    if plt is None:
        return

    cases = (
        ("Nominal", None, 0.0, "51_last_micro_nominal_S11_S21.png"),
        ("Q80/Cp40", 80.0, 40.0, "52_last_micro_Q80Cp40_S11_S21.png"),
        ("Q60/Cp60", 60.0, 60.0, "53_last_micro_Q60Cp60_S11_S21.png"),
    )

    for title, q, cp, filename in cases:
        s11_b, s21_b = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, before, low, high, qind=q, cp_fF=cp
        )
        s11_a, s21_a = simulate_dfr_3rx4_cellwise(
            f_ghz*1e9, after, low, high, qind=q, cp_fF=cp
        )

        fig = plt.figure(figsize=(9.5, 5.6))
        plt.plot(f_ghz, db20(s21_b), label=f"S21 before {title}")
        plt.plot(f_ghz, db20(s21_a), label=f"S21 after {title}")
        plt.plot(f_ghz, db20(s11_a), label=f"S11 after {title}")
        plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
        plt.axhline(-50.0, linewidth=0.8)
        plt.xlabel("Frequency (GHz)")
        plt.ylabel("Magnitude (dB)")
        plt.title(f"3Rx4 Last Micro-Trim - {title}")
        plt.ylim(-80, 2)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()
        fig.savefig(outdir/filename, dpi=220)
        plt.close(fig)


# =============================================================================
# 7. OPTIONAL TOUCHSTONE SIGN-OFF
# =============================================================================

def read_s2p(path: str | Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    unit_scale = 1.0
    fmt = "MA"
    freqs, s11, s21 = [], [], []

    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("!"):
                continue
            if line.startswith("#"):
                t = line.upper().split()
                unit_scale = (
                    1e9 if "GHZ" in t else
                    1e6 if "MHZ" in t else
                    1e3 if "KHZ" in t else 1.0
                )
                for candidate in ("RI", "MA", "DB"):
                    if candidate in t:
                        fmt = candidate
                continue

            vals = line.split()
            if len(vals) < 9:
                continue
            x = list(map(float, vals[:9]))
            f = x[0]*unit_scale

            def cplx(a, b):
                if fmt == "RI":
                    return a + 1j*b
                if fmt == "MA":
                    return a*np.exp(1j*np.deg2rad(b))
                return 10**(a/20)*np.exp(1j*np.deg2rad(b))

            # Touchstone 1.0 order: S11 S21 S12 S22
            freqs.append(f)
            s11.append(cplx(x[1], x[2]))
            s21.append(cplx(x[3], x[4]))

    if not freqs:
        raise ValueError(f"No S2P data parsed from {path}")
    return np.asarray(freqs), np.asarray(s11), np.asarray(s21)


def verify_s2p(path: str | Path) -> dict:
    f, s11, s21 = read_s2p(path)
    return metrics(f/1e9, s11, s21)


# =============================================================================
# 7B. AUTONOMOUS ENGINEERING AGENT V2 — COHERE PLANNER + REAL TOOL CALLING
# =============================================================================

@dataclass(frozen=True)
class AgentGoal:
    nominal_ripple_max_dB: float = 0.54
    q80_cp40_ripple_max_dB: float = 0.65
    q60_cp60_ripple_max_dB: float = 0.75
    rejection_min_dB: float = 45.0


def evaluate_agent_goal(v: dict, goal: AgentGoal) -> dict:
    """Python-authoritative goal evaluation using strict inequalities."""
    n, q80, q60 = v["nominal"], v["Q80_Cp40"], v["Q60_Cp60"]
    rej = {
        f"{name}_{side}": v[name][side]
        for name in ("nominal", "Q80_Cp40", "Q60_Cp60")
        for side in ("lower_stopband_min_rejection_dB", "upper_stopband_min_rejection_dB")
    }
    checks = {
        "nominal_ripple": n["passband_ripple_dB"] < goal.nominal_ripple_max_dB,
        "Q80_Cp40_ripple": q80["passband_ripple_dB"] < goal.q80_cp40_ripple_max_dB,
        "Q60_Cp60_ripple": q60["passband_ripple_dB"] < goal.q60_cp60_ripple_max_dB,
        "rejection": all(x > goal.rejection_min_dB for x in rej.values()),
    }
    margins = {
        "nominal_ripple_margin_dB": goal.nominal_ripple_max_dB - n["passband_ripple_dB"],
        "Q80_Cp40_ripple_margin_dB": goal.q80_cp40_ripple_max_dB - q80["passband_ripple_dB"],
        "Q60_Cp60_ripple_margin_dB": goal.q60_cp60_ripple_max_dB - q60["passband_ripple_dB"],
        "worst_rejection_margin_dB": min(rej.values()) - goal.rejection_min_dB,
    }
    return {
        "satisfied": all(checks.values()),
        "checks": checks,
        "margins": margins,
        "rejection_values_dB": rej,
    }


def compact_agent_state(v: dict, goal: AgentGoal) -> dict:
    """Compact, verified state sent to the planner. No unverified RF claims."""
    ev = evaluate_agent_goal(v, goal)
    return {
        "goal": asdict(goal),
        "evaluation": ev,
        "metrics": {
            name: {
                "ripple_dB": v[name]["passband_ripple_dB"],
                "minimum_IL_dB": v[name]["minimum_IL_dB"],
                "worst_IL_dB": v[name]["worst_passband_IL_dB"],
                "BW_3dB_GHz": v[name]["BW_3dB_GHz"],
                "worst_S11_dB": v[name]["worst_S11_dB"],
                "far_rejection_low_dB": v[name]["lower_stopband_min_rejection_dB"],
                "far_rejection_high_dB": v[name]["upper_stopband_min_rejection_dB"],
            }
            for name in ("nominal", "Q80_Cp40", "Q60_Cp60")
        },
    }


def deterministic_planner(v: dict, goal: AgentGoal) -> dict:
    """Offline / API-failure fallback. Returns the same action vocabulary as Cohere tools."""
    ev = evaluate_agent_goal(v, goal)
    if ev["satisfied"]:
        return {
            "tool": "stop_if_satisfied",
            "arguments": {"reason": "All Python-verified constraints are satisfied."},
            "source": "deterministic_fallback",
        }
    if not ev["checks"]["rejection"]:
        return {
            "tool": "recover_rejection",
            "arguments": {"reason": "At least one verified far-stop rejection is below target."},
            "source": "deterministic_fallback",
        }
    ripple_margins = {
        "nominal": ev["margins"]["nominal_ripple_margin_dB"],
        "Q80_Cp40": ev["margins"]["Q80_Cp40_ripple_margin_dB"],
        "Q60_Cp60": ev["margins"]["Q60_Cp60_ripple_margin_dB"],
    }
    focus = min(ripple_margins, key=ripple_margins.get)
    return {
        "tool": "optimize_ripple",
        "arguments": {
            "focus_scenario": focus,
            "reason": f"Worst verified ripple margin is {focus}.",
        },
        "source": "deterministic_fallback",
    }


COHERE_ENGINEERING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_verified_design",
            "description": (
                "Return the current Python-verified FBAW metrics and hard-constraint margins. "
                "Use when another inspection is needed before choosing an optimization action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why inspection is useful now."}
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_ripple",
            "description": (
                "Run the existing physics-constrained ripple optimization branch. Python performs "
                "all numerical simulation and verification; the model only chooses the scenario focus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus_scenario": {
                        "type": "string",
                        "enum": ["nominal", "Q80_Cp40", "Q60_Cp60"],
                        "description": "Verified scenario with the most important ripple deficit.",
                    },
                    "reason": {"type": "string", "description": "Short engineering rationale."},
                },
                "required": ["focus_scenario", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recover_rejection",
            "description": (
                "Run the existing lower-stopband/far-rejection recovery tool before further ripple work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why rejection recovery has priority."}
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "controlled_failure_probe",
            "description": (
                "TEST-ONLY reliability tool. It intentionally returns one controlled execution failure, "
                "changes no RF values, and forces safe re-planning from the returned Python state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the controlled failure probe is being run."}
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "realistic_constraint_conflict_probe",
            "description": (
                "RELIABILITY EVALUATION TOOL. Python generates and simulates physically valid but deliberately aggressive "
                "local candidates. It looks for a real RF tradeoff where Q60 ripple improves locally but the overall hard-goal "
                "state worsens. Such a candidate is rejected and rolled back by the normal Python acceptance rule. "
                "No RF metrics are invented; if no such conflict is found, the tool reports no_conflict_found."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why a real constraint-conflict probe is useful now."}
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_if_satisfied",
            "description": (
                "Request STOP. Python will permit STOP only when every hard goal is independently verified."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the planner believes the task is complete."}
                },
                "required": ["reason"],
            },
        },
    },
]


def _tool_subset(*names: str) -> list:
    """Return only the named Cohere tools, preserving their schemas."""
    wanted = set(names)
    return [
        t for t in COHERE_ENGINEERING_TOOLS
        if t.get("function", {}).get("name") in wanted
    ]


def _stress_allowed_tools(
    trace: list, current_v: dict, goal: AgentGoal,
    failure_recovery_test: bool = False,
    realistic_failure_test: bool = False,
) -> list:
    """Enforced V4.1 evaluation state machine."""
    tools_seen = [
        (r.get("planner", {}) or {}).get("tool")
        for r in trace if r.get("planner")
    ]
    ev = evaluate_agent_goal(current_v, goal)
    if "inspect_verified_design" not in tools_seen:
        return _tool_subset("inspect_verified_design")
    if realistic_failure_test and "realistic_constraint_conflict_probe" not in tools_seen:
        return _tool_subset("realistic_constraint_conflict_probe")
    if failure_recovery_test and "controlled_failure_probe" not in tools_seen:
        return _tool_subset("controlled_failure_probe")
    if ev["satisfied"]:
        return _tool_subset("stop_if_satisfied")
    return _tool_subset("optimize_ripple", "recover_rejection")


def _cohere_tool_result_message(tool_call_id: str, payload: dict) -> dict:
    """Cohere Chat V2 tool-result message."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": [
            {
                "type": "document",
                "document": {"data": json.dumps(jsonable(payload))},
            }
        ],
    }


def _extract_cohere_tool_call(response) -> tuple[Optional[dict], Optional[object]]:
    calls = getattr(getattr(response, "message", None), "tool_calls", None) or []
    if not calls:
        return None, None
    tc = calls[0]
    fn = getattr(tc, "function", None)
    name = getattr(fn, "name", None)
    raw_args = getattr(fn, "arguments", "{}") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except Exception:
        args = {}
    return {
        "tool": name,
        "arguments": args,
        "tool_call_id": getattr(tc, "id", "unknown_tool_call"),
        "source": "cohere_tool_call",
        "tool_plan": getattr(getattr(response, "message", None), "tool_plan", None),
    }, tc


def make_cohere_agent_client():
    key = os.getenv("COHERE_API_KEY")
    if not key:
        return None, "COHERE_API_KEY not set"
    try:
        import cohere
        return cohere.ClientV2(api_key=key), None
    except Exception as exc:
        return None, f"Cohere client unavailable: {exc}"


def realistic_constraint_conflict_probe(
    current: CellwiseDesign,
    current_v: dict,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    goal: AgentGoal,
) -> tuple[CellwiseDesign, dict, dict]:
    """
    Search for a *real simulated* engineering tradeoff candidate.

    The probe is deterministic and does not fabricate a failure. It evaluates
    physically valid perturbations around the current checkpoint and prefers a
    point that improves Q60/Cp60 ripple locally while worsening the aggregate
    hard-goal state enough that the normal Python acceptance rule rejects it.
    The accepted design state is never changed by this probe.
    """
    before_ev = evaluate_agent_goal(current_v, goal)
    fail_before = sum(not x for x in before_ev["checks"].values())
    worst_before = min(before_ev["margins"].values())
    q60_before = current_v["Q60_Cp60"]["passband_ripple_dB"]

    candidates = []

    # Global matching perturbations: realistic aggressive local experiments.
    scales = (0.88, 0.92, 0.96, 1.04, 1.08, 1.12)
    for s4 in scales:
        for s6 in scales:
            if s4 == 1.0 and s6 == 1.0:
                continue
            d = CellwiseDesign(
                cells=current.cells,
                L4_nH=max(0.05, current.L4_nH*s4),
                L6_nH=max(0.05, current.L6_nH*s6),
            )
            candidates.append((f"global_L4x{s4:.2f}_L6x{s6:.2f}", d))

    # Cell-local perturbations in parameters that commonly trade passband shape
    # against robustness. Only one cell parameter moves in each candidate.
    for ci, cell in enumerate(current.cells):
        for field in ("L3_nH", "C1_pF", "L7a_nH", "L7b_nH", "L7c_nH"):
            for sc in (0.85, 0.90, 1.10, 1.15):
                c2 = replace(cell, **{field: max(1e-6, getattr(cell, field)*sc)})
                d = replace_cell(current, ci, c2)
                candidates.append((f"cell{ci+1}_{field}x{sc:.2f}", d))

    best = None
    for label, cand in candidates:
        cand_v = verify_cellwise_extended(cand, low, high, f_ghz)
        after_ev = evaluate_agent_goal(cand_v, goal)
        fail_after = sum(not x for x in after_ev["checks"].values())
        worst_after = min(after_ev["margins"].values())
        q60_after = cand_v["Q60_Cp60"]["passband_ripple_dB"]

        accepted_by_normal_rule = (
            fail_after < fail_before
            or (fail_after == fail_before and worst_after > worst_before + 1e-12)
        )
        local_q60_improved = q60_after < q60_before - 1e-5
        aggregate_worsened = (fail_after > fail_before) or (worst_after < worst_before - 1e-5)

        # Primary realistic failure: a locally tempting Q60 improvement that the
        # system must reject because aggregate hard-goal health got worse.
        if local_q60_improved and aggregate_worsened and not accepted_by_normal_rule:
            score = (q60_before-q60_after) + 0.5*max(0.0, worst_before-worst_after) + 0.5*max(0, fail_after-fail_before)
            rec = (score, label, cand, cand_v, after_ev, fail_after, worst_after, q60_after)
            if best is None or rec[0] > best[0]:
                best = rec

    if best is None:
        return current, current_v, {
            "tool": "realistic_constraint_conflict_probe",
            "accepted": False,
            "rollback": False,
            "changed_design": False,
            "realistic_failure_observed": False,
            "no_conflict_found": True,
            "reason": "No simulated candidate both improved Q60 ripple and worsened aggregate hard-goal health under the configured deterministic probe set.",
            "state": compact_agent_state(current_v, goal),
        }

    _, label, cand, cand_v, after_ev, fail_after, worst_after, q60_after = best
    return current, current_v, {
        "tool": "realistic_constraint_conflict_probe",
        "accepted": False,
        "rollback": True,
        "changed_design": False,
        "realistic_failure_observed": True,
        "failure_type": "simulated_constraint_conflict",
        "candidate_label": label,
        "candidate_parameters": cand.to_dict(),
        "local_improvement": {
            "Q60_Cp60_ripple_before_dB": q60_before,
            "Q60_Cp60_ripple_candidate_dB": q60_after,
            "improvement_dB": q60_before-q60_after,
        },
        "aggregate_evaluation": {
            "failed_constraints_before": fail_before,
            "failed_constraints_candidate": fail_after,
            "worst_margin_before_dB": worst_before,
            "worst_margin_candidate_dB": worst_after,
            "candidate_goal_evaluation": after_ev,
        },
        "rollback_reason": "Candidate was generated and RF-simulated by Python, but rejected by the normal aggregate acceptance rule; verified checkpoint preserved.",
        "state": compact_agent_state(current_v, goal),
    }


def execute_engineering_tool(
    tool_name: str,
    tool_args: dict,
    current,
    current_v: dict,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    goal: AgentGoal,
):
    """
    Execute one planner-selected tool.

    Safety/reliability invariant:
      - Cohere never supplies component values or RF metrics.
      - Python owns simulation, candidate generation, verification, acceptance, rollback, and STOP.
    """
    before = current
    before_v = current_v
    before_ev = evaluate_agent_goal(before_v, goal)
    search_df = pd.DataFrame()

    if tool_name == "inspect_verified_design":
        return current, current_v, {
            "tool": tool_name,
            "accepted": True,
            "changed_design": False,
            "state": compact_agent_state(current_v, goal),
        }, search_df

    if tool_name == "realistic_constraint_conflict_probe":
        cur, cur_v, payload = realistic_constraint_conflict_probe(
            current, current_v, low, high, f_ghz, goal
        )
        return cur, cur_v, payload, search_df

    if tool_name == "controlled_failure_probe":
        return current, current_v, {
            "tool": tool_name,
            "accepted": False,
            "rollback": True,
            "changed_design": False,
            "failure_injected": True,
            "failure_type": "controlled_tool_execution_failure",
            "error": "Injected test failure before any design mutation.",
            "recovery_required": True,
            "state": compact_agent_state(current_v, goal),
        }, search_df

    if tool_name == "stop_if_satisfied":
        allowed = bool(before_ev["satisfied"])
        return current, current_v, {
            "tool": tool_name,
            "accepted": allowed,
            "stop_allowed": allowed,
            "reason": (
                "STOP accepted by Python verifier."
                if allowed else
                "STOP rejected: one or more Python-verified constraints still fail."
            ),
            "state": compact_agent_state(current_v, goal),
        }, search_df

    if tool_name == "recover_rejection":
        cand, cand_v, _, _ = final_lower_stopband_recovery(current, low, high, f_ghz)
    elif tool_name == "optimize_ripple":
        # The focus_scenario is planner context. Existing RF optimizer remains the numerical authority.
        cand, cand_v, _, search_df, _ = ripple_optimized_45db_branch(current, low, high, f_ghz)
    else:
        return current, current_v, {
            "tool": tool_name,
            "accepted": False,
            "error": "Unknown or disallowed tool. No design change was made.",
            "state": compact_agent_state(current_v, goal),
        }, search_df

    after_ev = evaluate_agent_goal(cand_v, goal)
    fail_before = sum(not x for x in before_ev["checks"].values())
    fail_after = sum(not x for x in after_ev["checks"].values())
    worst_before = min(before_ev["margins"].values())
    worst_after = min(after_ev["margins"].values())

    # Acceptance is Python-only and deliberately conservative.
    accepted = (
        fail_after < fail_before
        or (fail_after == fail_before and worst_after > worst_before + 1e-12)
    )

    if accepted:
        current, current_v = cand, cand_v
    else:
        current, current_v = before, before_v

    result = {
        "tool": tool_name,
        "planner_arguments": tool_args,
        "accepted": bool(accepted),
        "rollback": bool(not accepted),
        "failed_constraints_before": fail_before,
        "failed_constraints_after_candidate": fail_after,
        "worst_margin_before_dB": worst_before,
        "worst_margin_after_candidate_dB": worst_after,
        "candidate_evaluation": after_ev,
        "accepted_state": compact_agent_state(current_v, goal),
    }
    return current, current_v, result, search_df


def run_engineering_agent_v3(
    start,
    low: MBVD,
    high: MBVD,
    f_ghz: np.ndarray,
    goal: AgentGoal,
    model: str,
    max_agent_steps: int = 5,
    use_cohere: bool = True,
    stress_test: bool = False,
    failure_recovery_test: bool = False,
    realistic_failure_test: bool = False,
):
    """
    Cohere Planner -> function/tool call -> Python RF tool -> Python evaluator
    -> accept/rollback -> feed tool result back -> retry or STOP.

    The model orchestrates. Python remains the numerical and acceptance authority.
    """
    current = start
    current_v = verify_cellwise_extended(current, low, high, f_ghz)
    trace, dfs = [], []

    co = None
    cohere_error = None
    if use_cohere:
        co, cohere_error = make_cohere_agent_client()

    system = (
        "You are the planning layer of an autonomous, physics-constrained FBAW engineering agent. "
        "You MUST use one of the supplied tools to take the next action. Never invent S-parameters, "
        "component values, or performance. Python is the numerical authority and may reject STOP or "
        "roll back an optimization. Prefer recover_rejection when rejection fails; otherwise optimize "
        "the ripple scenario with the worst negative margin. Request STOP only when the Python-verified "
        "state says satisfied=true. After a rollback, use the returned verified state to choose the next tool."
    )
    if stress_test:
        system += (
            " STRESS-TEST PROTOCOL: first call inspect_verified_design before any optimization. "
            "After every tool result, explicitly re-plan from the returned Python-verified state. "
            "When all goals are satisfied, explicitly call stop_if_satisfied; do not merely state completion."
        )
        if failure_recovery_test:
            system += (
                " FAILURE-RECOVERY PROTOCOL: after inspection, call controlled_failure_probe. "
                "Read its controlled failure result, then re-plan and choose a real optimization/recovery tool. "
                "Do not STOP because of the injected failure."
            )
        if realistic_failure_test:
            system += (
                " REALISTIC-FAILURE PROTOCOL: after inspection, call realistic_constraint_conflict_probe. "
                "This tool performs real Python RF simulations and may return a candidate that locally improves Q60 ripple "
                "but is rejected by aggregate hard-goal evaluation. Read the exact rollback evidence, then re-plan and choose "
                "a real optimization/recovery tool. Never claim a conflict if the tool reports no_conflict_found."
            )
        user_content = (
            "Run the multi-step agent evaluation. The hard goal is: "
            + json.dumps(jsonable(asdict(goal)))
            + ". Do not assume the current RF state; inspect it with the inspection tool first."
        )
    else:
        user_content = (
            "Optimize this FBAW filter to the following hard goal. Current state is Python-verified:\n"
            + json.dumps(jsonable(compact_agent_state(current_v, goal)), indent=2)
        )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    for step in range(1, max_agent_steps + 1):
        before_ev = evaluate_agent_goal(current_v, goal)
        if before_ev["satisfied"] and not stress_test:
            trace.append({
                "step": step,
                "decision": {"tool": "STOP", "source": "python_precheck"},
                "evaluation": before_ev,
            })
            return current, current_v, trace, pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(), True

        decision = None
        response = None
        if co is not None:
            try:
                allowed_tools = (
                    _stress_allowed_tools(
                        trace, current_v, goal, failure_recovery_test, realistic_failure_test
                    )
                    if stress_test else COHERE_ENGINEERING_TOOLS
                )
                response = co.chat(
                    model=model,
                    messages=messages,
                    tools=allowed_tools,
                    strict_tools=True,
                )
                decision, _ = _extract_cohere_tool_call(response)
                if decision is not None:
                    messages.append(response.message)
            except Exception as exc:
                cohere_error = str(exc)
                decision = None

        if decision is None:
            if stress_test:
                inspection_seen = any(
                    (r.get("planner", {}) or {}).get("tool") == "inspect_verified_design"
                    for r in trace
                )
                ev_now = evaluate_agent_goal(current_v, goal)
                failure_seen = any(
                    (r.get("planner", {}) or {}).get("tool") == "controlled_failure_probe"
                    for r in trace
                )
                realistic_seen = any(
                    (r.get("planner", {}) or {}).get("tool") == "realistic_constraint_conflict_probe"
                    for r in trace
                )
                if not inspection_seen:
                    decision = {
                        "tool": "inspect_verified_design",
                        "arguments": {"reason": "Stress-test phase 1 requires verified-state inspection."},
                        "source": "deterministic_fallback",
                    }
                elif realistic_failure_test and not realistic_seen:
                    decision = {
                        "tool": "realistic_constraint_conflict_probe",
                        "arguments": {"reason": "V4.1 requires one real simulated constraint-conflict probe before recovery."},
                        "source": "deterministic_fallback",
                    }
                elif failure_recovery_test and not failure_seen:
                    decision = {
                        "tool": "controlled_failure_probe",
                        "arguments": {"reason": "V4 requires one controlled failure before recovery."},
                        "source": "deterministic_fallback",
                    }
                elif ev_now["satisfied"]:
                    decision = {
                        "tool": "stop_if_satisfied",
                        "arguments": {"reason": "Python-verified state satisfies every hard goal."},
                        "source": "deterministic_fallback",
                    }
                else:
                    decision = deterministic_planner(current_v, goal)
            else:
                decision = deterministic_planner(current_v, goal)
            if cohere_error:
                decision["cohere_error"] = cohere_error

        tool_name = decision.get("tool")
        tool_args = decision.get("arguments") or {}
        print("\n" + "="*78)
        print(f"COHERE ENGINEERING AGENT V4.1 STEP {step}")
        print("="*78)
        print("Planner:", decision.get("source"))
        if stress_test:
            inspection_seen_now = any(
                (r.get("planner", {}) or {}).get("tool") == "inspect_verified_design"
                for r in trace
            )
            ev_now = evaluate_agent_goal(current_v, goal)
            failure_seen_now = any(
                (r.get("planner", {}) or {}).get("tool") == "controlled_failure_probe"
                for r in trace
            )
            realistic_seen_now = any(
                (r.get("planner", {}) or {}).get("tool") == "realistic_constraint_conflict_probe"
                for r in trace
            )
            phase = (
                "INSPECT" if not inspection_seen_now else
                "REALISTIC_CONSTRAINT_CONFLICT" if realistic_failure_test and not realistic_seen_now else
                "CONTROLLED_FAILURE" if failure_recovery_test and not failure_seen_now else
                "EXPLICIT_STOP" if ev_now["satisfied"] else
                "RECOVERY_REPLAN" if ((realistic_failure_test and realistic_seen_now) or (failure_recovery_test and failure_seen_now)) else
                "OPTIMIZE_OR_RECOVER"
            )
            print("Stress-test phase:", phase)
        if decision.get("tool_plan"):
            print("Tool plan:", decision["tool_plan"])
        print("Tool call:", tool_name, json.dumps(tool_args))

        current, current_v, tool_result, sdf = execute_engineering_tool(
            tool_name, tool_args, current, current_v, low, high, f_ghz, goal
        )
        if not sdf.empty:
            sdf = sdf.copy()
            sdf["agent_step"] = step
            sdf["planner_tool"] = tool_name
            dfs.append(sdf)

        rec = {
            "step": step,
            "planner": decision,
            "tool_result": tool_result,
            "evaluation_after": evaluate_agent_goal(current_v, goal),
        }
        trace.append(rec)
        print("Python result:", json.dumps(jsonable(tool_result), indent=2))

        # Feed the exact Python tool result back into Cohere's multi-step tool-use history.
        if co is not None and decision.get("source") == "cohere_tool_call":
            messages.append(_cohere_tool_result_message(
                decision.get("tool_call_id", "unknown_tool_call"),
                tool_result,
            ))

        if tool_name == "stop_if_satisfied" and tool_result.get("stop_allowed"):
            return current, current_v, trace, pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(), True

        if evaluate_agent_goal(current_v, goal)["satisfied"] and not stress_test:
            # Normal mode may terminate immediately after Python verification.
            trace.append({
                "step": step,
                "decision": {"tool": "STOP", "source": "python_postcheck"},
                "evaluation": evaluate_agent_goal(current_v, goal),
            })
            return current, current_v, trace, pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(), True

    final_satisfied = evaluate_agent_goal(current_v, goal)["satisfied"]
    if stress_test:
        explicit_stop = any(
            (r.get("planner", {}) or {}).get("tool") == "stop_if_satisfied"
            and (r.get("tool_result", {}) or {}).get("stop_allowed")
            for r in trace
        )
        final_satisfied = bool(final_satisfied and explicit_stop)
    return (
        current,
        current_v,
        trace,
        pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(),
        final_satisfied,
    )


# =============================================================================
# 8. OUTPUTS / PLOTS
# =============================================================================

def jsonable(obj):
    if isinstance(obj, Design):
        return obj.to_dict()
    if isinstance(obj, MBVD):
        return asdict(obj)
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, complex):
        return {"real": obj.real, "imag": obj.imag}
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


def plot_response(
    outdir: Path,
    f_ghz: np.ndarray,
    low: MBVD,
    high: MBVD,
    baseline: Design,
    prellm: Design,
    final: Design,
) -> None:
    if plt is None:
        return

    fig = plt.figure(figsize=(9, 5.5))
    for label, d in [
        ("Baseline", baseline),
        ("Pareto selected", prellm),
        ("Final re-verified", final),
    ]:
        _, s21 = simulate_dfr_3rxn(
            f_ghz*1e9, d, low, high, 4,
            qind=60.0, cp_total_fF=60.0
        )
        plt.plot(f_ghz, db20(s21), label=label)

    plt.axvspan(PASSBAND_GHZ[0], PASSBAND_GHZ[1], alpha=0.08)
    plt.xlabel("Frequency (GHz)")
    plt.ylabel("S21 (dB)")
    plt.title("DFR 3Rx4 - Qind=60, Cp=60 fF")
    plt.ylim(-100, 5)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    fig.savefig(outdir/"final_response.png", dpi=220)
    plt.close(fig)


# =============================================================================
# 9. MAIN CLOSED LOOP
# =============================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="COMSOL -> MBVD -> DFR 3Rx4 -> Q60/Cp60 robustness trim."
    )
    p.add_argument("--comsol-low", help="COMSOL export for ~6.22 GHz DFR resonator")
    p.add_argument("--comsol-high", help="COMSOL export for ~7.40 GHz DFR resonator")
    p.add_argument("--comsol-sfr", help="COMSOL export for ~7.49 GHz SFR synthesis resonator")
    p.add_argument("--vsrc", type=float, default=5.0)
    p.add_argument("--samples", type=int, default=1200, help="Pareto candidate count")
    p.add_argument("--seed", type=int, default=20260818)
    p.add_argument("--freq-points", type=int, default=1001)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument(
        "--cohere-model",
        default=os.getenv("COHERE_MODEL", "command-a-plus-05-2026"),
    )
    p.add_argument("--ads-s2p", help="Optional ADS/EM Touchstone file for independent sign-off")
    p.add_argument("--outdir", default="fbaw_3Rx4_robustness_output")
    p.add_argument("--verbose-fit", action="store_true")
    p.add_argument("--goal-nominal-ripple", type=float, default=0.54)
    p.add_argument("--goal-q80-ripple", type=float, default=0.65)
    p.add_argument("--goal-q60-ripple", type=float, default=0.75)
    p.add_argument("--goal-rejection", type=float, default=45.0)
    p.add_argument("--agent-steps", type=int, default=5)
    p.add_argument("--no-cohere-planner", action="store_true",
                   help="Use deterministic planner fallback; still executes the same Python tools")
    p.add_argument("--stress-test", action="store_true",
                   help="Multi-step agent evaluation: inspect first, re-plan after tool results, and require explicit STOP")
    p.add_argument("--failure-recovery-test", action="store_true",
                   help="V4.1 reliability test: inspect -> controlled failure -> recovery re-plan -> explicit STOP; implies --stress-test")
    p.add_argument("--realistic-failure-test", action="store_true",
                   help="V4.1 realistic test: inspect -> real simulated constraint-conflict rejection/rollback -> recovery re-plan -> explicit STOP; implies --stress-test")
    return p.parse_args()


def maybe_fit(
    arg: Optional[str],
    seed: MBVD,
    outdir: Path,
    vsrc: float,
    verbose: bool,
) -> MBVD:
    if not arg:
        return seed
    fitted, curve = fit_mbvd_from_comsol(arg, seed, vsrc=vsrc, verbose=verbose)
    curve.to_csv(outdir/f"{seed.name}_COMSOL_MBVD_fit.csv", index=False)
    return fitted


def main() -> int:
    args = parse_args()
    if args.failure_recovery_test or args.realistic_failure_test:
        args.stress_test = True
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print("="*78)
    print("FBAW CLOSED LOOP")
    print("3Rx4 FINAL 50-dB CHECKPOINT -> RIPPLE-OPTIMIZED >45-dB BRANCH")
    print("Only one L3/L7 parameter in one cell moves at a time")
    print("="*78)

    low = maybe_fit(
        args.comsol_low, MBVD_SEEDS["LOW_6p22"],
        outdir, args.vsrc, args.verbose_fit
    )
    high = maybe_fit(
        args.comsol_high, MBVD_SEEDS["HIGH_7p40"],
        outdir, args.vsrc, args.verbose_fit
    )
    f_ghz = np.linspace(5.5, 8.4, args.freq_points)

    # Rebuild balanced-selected checkpoint.
    start = make_uniform_cellwise_start()
    coarse_final, _, _, _ = cell_by_cell_nominal_optimize(
        start, low, high, f_ghz
    )
    fine_final, _, _ = fine_cyclic_nominal_trim(
        coarse_final, low, high, f_ghz
    )
    terminal_final, _, _ = final_terminal_trim(
        fine_final, low, high, f_ghz
    )
    nominal_final, _, _ = l6_directed_extension(
        terminal_final, low, high, f_ghz
    )
    _, _, robustness_history = q60_cell_by_cell_robustness_trim(
        nominal_final, low, high, f_ghz
    )
    (_, best_label, selected, selected_v), _ = (
        collect_and_select_balanced_checkpoint(
            nominal_final, robustness_history, low, high, f_ghz
        )
    )

    # Reproduce previous lower-stopband recovery checkpoint.
    recovery_final, recovery_v, recovery_history, recovery_ok = (
        final_lower_stopband_recovery(
            selected, low, high, f_ghz
        )
    )

    # New last micro stage.
    final, final_v, last_history, last_ok = final_last_micro_trim(
        recovery_final, low, high, f_ghz
    )

    # NEW FINAL CLOSURE: freeze all cell values and use only global L4/L6 to
    # close the remaining ~0.02 dB lower-stop gap under strict passband guards.
    ultra_start = final
    ultra_start_v = final_v
    final, final_v, ultra_df, ultra_ok = ultrafine_global_l4l6_closure(
        ultra_start, low, high, f_ghz
    )
    last_ok = bool(ultra_ok)
    ultra_df.to_csv(outdir/"56_ultrafine_L4L6_closure.csv", index=False)

    # Final cell-local closure: only L3 is reopened, followed by tiny global L4/L6 compensation.
    l3_start = final
    l3_start_v = final_v
    final, final_v, l3_history, l3_df, l3_ok = ultramicro_l3_with_l4l6_compensation(
        l3_start, low, high, f_ghz
    )
    last_ok = bool(l3_ok)
    l3_df.to_csv(outdir/"57_ultramicro_L3_L4L6_closure.csv", index=False)

    # Preserve the successful >=50-dB checkpoint, then branch independently toward lower ripple.
    final_50db = final
    final_50db_v = final_v
    goal = AgentGoal(
        nominal_ripple_max_dB=args.goal_nominal_ripple,
        q80_cp40_ripple_max_dB=args.goal_q80_ripple,
        q60_cp60_ripple_max_dB=args.goal_q60_ripple,
        rejection_min_dB=args.goal_rejection,
    )
    ripple_final, ripple_v, ripple_history, ripple_df, ripple_ok = run_engineering_agent_v3(
        final_50db, low, high, f_ghz, goal,
        model=args.cohere_model,
        max_agent_steps=args.agent_steps,
        use_cohere=(not args.no_llm and not args.no_cohere_planner),
        stress_test=args.stress_test,
        failure_recovery_test=args.failure_recovery_test,
        realistic_failure_test=args.realistic_failure_test,
    )
    ripple_df.to_csv(outdir/"58_engineering_agent_search.csv", index=False)

    plot_last_micro_trim(
        outdir, f_ghz, low, high, final_50db, ripple_final
    )

    rows = []
    for label, vv in (
        ("balanced_selected", selected_v),
        ("previous_recovery", recovery_v),
        ("preserved_50dB_final", final_50db_v),
        ("ripple_optimized_45dB", ripple_v),
    ):
        for scenario in ("nominal", "Q80_Cp40", "Q60_Cp60"):
            rows.append(_metric_row(label, scenario, vv[scenario]))

    pd.DataFrame(rows).to_csv(
        outdir/"54_last_micro_trim_metrics.csv", index=False
    )

    planner_sequence = [
        (r.get("planner", {}) or {}).get("tool")
        for r in ripple_history if r.get("planner")
    ]
    failure_seen = any(
        (r.get("tool_result", {}) or {}).get("failure_injected")
        for r in ripple_history
    )
    realistic_failure_seen = any(
        (r.get("tool_result", {}) or {}).get("realistic_failure_observed")
        for r in ripple_history
    )
    rollback_count = sum(
        1 for r in ripple_history if (r.get("tool_result", {}) or {}).get("rollback")
    )
    recovery_after_failure = False
    recovery_after_realistic_failure = False
    if "controlled_failure_probe" in planner_sequence:
        fi = planner_sequence.index("controlled_failure_probe")
        recovery_after_failure = any(
            t in ("optimize_ripple", "recover_rejection")
            for t in planner_sequence[fi+1:]
        )
    if "realistic_constraint_conflict_probe" in planner_sequence:
        fi = planner_sequence.index("realistic_constraint_conflict_probe")
        recovery_after_realistic_failure = any(
            t in ("optimize_ripple", "recover_rejection")
            for t in planner_sequence[fi+1:]
        )

    stress_eval = {
        "enabled": bool(args.stress_test),
        "failure_recovery_test": bool(args.failure_recovery_test),
        "realistic_failure_test": bool(args.realistic_failure_test),
        "required_sequence": (
            ["inspect_verified_design", "realistic_constraint_conflict_probe", "optimization_or_recovery", "stop_if_satisfied"]
            if args.realistic_failure_test else
            ["inspect_verified_design", "controlled_failure_probe", "optimization_or_recovery", "stop_if_satisfied"]
            if args.failure_recovery_test else
            ["inspect_verified_design", "optimization_or_recovery", "stop_if_satisfied"]
        ),
        "planner_sequence": planner_sequence,
        "cohere_tool_calls": sum(
            1 for r in ripple_history
            if (r.get("planner", {}) or {}).get("source") == "cohere_tool_call"
        ),
        "inspection_seen": "inspect_verified_design" in planner_sequence,
        "controlled_failure_seen": bool(failure_seen),
        "realistic_failure_seen": bool(realistic_failure_seen),
        "recovery_after_failure": bool(recovery_after_failure),
        "recovery_after_realistic_failure": bool(recovery_after_realistic_failure),
        "explicit_stop_seen": any(
            (r.get("planner", {}) or {}).get("tool") == "stop_if_satisfied"
            and (r.get("tool_result", {}) or {}).get("stop_allowed")
            for r in ripple_history
        ),
        "rollback_count": rollback_count,
        "multi_step_pass": bool(
            "inspect_verified_design" in planner_sequence
            and any(t in ("optimize_ripple", "recover_rejection") for t in planner_sequence)
            and any(
                (r.get("planner", {}) or {}).get("tool") == "stop_if_satisfied"
                and (r.get("tool_result", {}) or {}).get("stop_allowed")
                for r in ripple_history
            )
            and (not args.failure_recovery_test or (failure_seen and recovery_after_failure and rollback_count >= 1))
            and (not args.realistic_failure_test or (realistic_failure_seen and recovery_after_realistic_failure and rollback_count >= 1))
        ),
    }

    report = {
        "purpose": (
            "Preserve the verified >=50 dB checkpoint, then run an independent ripple-first "
            "branch with far-stop rejection relaxed to >=45 dB and a Q60/Cp60 ripple target <=0.80 dB."
        ),
        "selected_checkpoint_label": best_label,
        "previous_recovery_success": bool(recovery_ok),
        "last_micro_success": bool(last_ok),
        "windows_percent": [100*x for x in LAST_WINDOWS],
        "cell_order": [x+1 for x in LAST_CELL_ORDER],
        "parameter_order": list(LAST_PARAMETER_ORDER),
        "previous_recovery_parameters": recovery_final.to_dict(),
        "previous_recovery_metrics": recovery_v,
        "last_micro_history": last_history,
        "ultrafine_L4L6_windows_percent": [100*x for x in ULTRA_L4L6_WINDOWS],
        "ultrafine_start_parameters": ultra_start.to_dict(),
        "ultrafine_start_metrics": ultra_start_v,
        "ultrafine_success": bool(ultra_ok),
        "L3_ultramicro_windows_percent": [100*x for x in L3_ULTRA_WINDOWS],
        "L3_ultramicro_start_parameters": l3_start.to_dict(),
        "L3_ultramicro_start_metrics": l3_start_v,
        "L3_ultramicro_history": l3_history,
        "L3_ultramicro_success": bool(l3_ok),
        "preserved_50dB_parameters": final_50db.to_dict(),
        "preserved_50dB_metrics": final_50db_v,
        "ripple45_target_Q60_ripple_dB": R45_Q60_RIPPLE_TARGET_DB,
        "ripple45_rejection_min_dB": R45_REJECTION_MIN_DB,
        "agent_version": "V3.1_Cohere_Enforced_MultiStep_Evaluation",
        "agent_model": args.cohere_model,
        "agent_goal": asdict(goal),
        "agent_trace": ripple_history,
        "stress_test_evaluation": stress_eval,
        "agent_success": bool(ripple_ok),
        "final_parameters": ripple_final.to_dict(),
        "final_metrics": ripple_v,
    }

    (outdir/"59_3Rx4_ENGINEERING_AGENT_V4_1_RESULT.json").write_text(
        json.dumps(jsonable(report), indent=2),
        encoding="utf-8"
    )

    print("\n" + "="*78)
    print("3Rx4 AUTONOMOUS ENGINEERING AGENT V4.1 RESULT")
    print("="*78)
    print("Preserved >=50 dB checkpoint:", "YES" if l3_ok else "NO")
    print("Agent goal satisfied:", "YES" if ripple_ok else "NO")
    if args.stress_test:
        print("Stress-test evaluation:")
        print(json.dumps(stress_eval, indent=2))
    print(json.dumps(ripple_final.to_dict(), indent=2))

    for scenario in ("nominal", "Q80_Cp40", "Q60_Cp60"):
        m = ripple_v[scenario]
        print(f"\n{scenario}:")
        print(
            f"  ripple={m['passband_ripple_dB']:.6f} dB, "
            f"IL={m['minimum_IL_dB']:.6f} dB, "
            f"worstIL={m['worst_passband_IL_dB']:.6f} dB, "
            f"BW={m['BW_3dB_GHz']:.6f} GHz"
        )
        print(
            f"  S11worst={m['worst_S11_dB']:.6f} dB, "
            f"far-rej=({m['lower_stopband_min_rejection_dB']:.3f}, "
            f"{m['upper_stopband_min_rejection_dB']:.3f}) dB, "
            f"TZ=({m['TZL']['GHz']:.4f},{m['TZU']['GHz']:.4f})"
        )

    print("\nSaved:")
    print(" ", outdir/"51_last_micro_nominal_S11_S21.png")
    print(" ", outdir/"52_last_micro_Q80Cp40_S11_S21.png")
    print(" ", outdir/"53_last_micro_Q60Cp60_S11_S21.png")
    print(" ", outdir/"54_last_micro_trim_metrics.csv")
    print(" ", outdir/"56_ultrafine_L4L6_closure.csv")
    print(" ", outdir/"57_ultramicro_L3_L4L6_closure.csv")
    print(" ", outdir/"58_engineering_agent_search.csv")
    print(" ", outdir/"59_3Rx4_ENGINEERING_AGENT_V4_1_RESULT.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
