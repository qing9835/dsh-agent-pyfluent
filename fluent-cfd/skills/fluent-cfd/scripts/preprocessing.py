#!/usr/bin/env python3
"""
preprocessing.py — Pre-processing calculators for ANSYS Fluent CFD.

Two self-contained calculators used BEFORE touching the solver:

  1. Porous-medium resistance (transpiration cooling / porous zones).
       Ergun/Forchheimer: permeability K, viscous resistance 1/K, and the
       inertial resistance C2.

  2. Isentropic flow (total <-> static, Mach, speed of sound, mass flux).
       Optional real-gas gamma(T) integrator for variable-k, or k=1.4.

Use the outputs to set porous-zone resistances and inlet boundary conditions.

Usage:
  python preprocessing.py --porous            --dp <dp_m> --eps <epsilon>
  python preprocessing.py --isentropic         --ma <Ma> --t0 <T0_K> --p0 <P0_Pa> --exact
  python preprocessing.py --isentropic         --ma <Ma> --t0 <T0_K> --p0 <P0_Pa> --k 1.4
"""

from __future__ import annotations

import argparse
import math
import sys
from typing import Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Universal constants
# ---------------------------------------------------------------------------
R_UNIV = 8.314472          # J/(K mol)
M_AIR = 28.9634            # g/mol
Rg_AIR = R_UNIV / M_AIR * 1000  # ~287.06 J/(kg K)

# gamma(T) table (T in K, gamma dimensionless) — from the reference calc script
_GAMMA_TABLE: list[Tuple[float, float]] = [
    (175, 1.401), (200, 1.401), (225, 1.401), (250, 1.401), (275, 1.401),
    (300, 1.400), (325, 1.400), (350, 1.398), (375, 1.397), (400, 1.395),
    (450, 1.391), (500, 1.387), (550, 1.381), (600, 1.376), (650, 1.370),
    (700, 1.364), (750, 1.359), (800, 1.354), (850, 1.349), (900, 1.344),
    (950, 1.340), (1000, 1.336), (1050, 1.333), (1100, 1.329), (1150, 1.326),
    (1200, 1.323), (1250, 1.321), (1300, 1.319), (1350, 1.316), (1400, 1.314),
    (1500, 1.311), (1600, 1.308), (1700, 1.305), (1800, 1.302), (1900, 1.300),
]


# ---------------------------------------------------------------------------
# Porous medium
# ---------------------------------------------------------------------------
def porous_resistance(dp: float, epsilon: float) -> dict[str, float]:
    """Return permeability K, viscous resistance 1/K, inertial resistance C2.

    Parameters
    ----------
    dp : float
        Mean particle/pore diameter in m.
    epsilon : float
        Porosity (0..1).

    Returns
    -------
    dict
        Keys: 'k', 'viscous_resistance', 'inertial_resistance', 'f', 'c2_f_over_sqrtk'.
    """
    if not (0 < epsilon < 1):
        raise ValueError(f"epsilon must be in (0,1), got {epsilon}")
    if dp <= 0:
        raise ValueError(f"dp must be > 0, got {dp}")

    k = dp * dp * epsilon**3 / (150.0 * (1.0 - epsilon) ** 2)
    vis_res = 1.0 / k
    # Ergun inertial coefficient (C2) convention:
    c2 = 3.5 * (1.0 - epsilon) / (epsilon**3 * dp)
    # Reference grouping (informational only):
    f = 1.75 / (math.sqrt(150.0) * epsilon**1.5)
    c2_f_over_sqrtk = f / math.sqrt(k)
    return {
        "k": k,
        "viscous_resistance": vis_res,
        "inertial_resistance": c2,
        "f": f,
        "c2_f_over_sqrtk": c2_f_over_sqrtk,
    }


# ---------------------------------------------------------------------------
# Isentropic flow
# ---------------------------------------------------------------------------
def _gamma(t: float) -> float:
    """Interpolate gamma from the reference table (clamped at ends)."""
    if t <= _GAMMA_TABLE[0][0]:
        return _GAMMA_TABLE[0][1]
    if t >= _GAMMA_TABLE[-1][0]:
        return _GAMMA_TABLE[-1][1]
    for i in range(len(_GAMMA_TABLE) - 1):
        t0, g0 = _GAMMA_TABLE[i]
        t1, g1 = _GAMMA_TABLE[i + 1]
        if t0 <= t <= t1:
            frac = (t - t0) / (t1 - t0)
            return g0 + frac * (g1 - g0)
    return 1.4


def _trapezoid(y: Sequence[float], x: Sequence[float]) -> float:
    total = 0.0
    for i in range(1, len(y)):
        total += 0.5 * (x[i] - x[i - 1]) * (y[i] + y[i - 1])
    return total


def solve_isentropic(
    ma: float,
    t0: float,
    p0: float,
    k: Optional[float] = None,
    exact: bool = False,
    rg: float = Rg_AIR,
    blowing: float = 0.02,
) -> dict[str, float]:
    """Compute isentropic static conditions, sound speed, velocity, density, mass flux.

    Parameters
    ----------
    ma : float
        Mach number.
    t0 : float
        Total temperature K.
    p0 : float
        Total pressure Pa.
    k : float, optional
        Ratio of specific heats. If None and exact=False, defaults to 1.4.
    exact : bool
        If True, use variable gamma(T) integrator (energy + entropy balance).
    rg : float
        Specific gas constant (J/(kg K)), default dry air.
    blowing : float
        Coolant/main blowing ratio F.

    Returns
    -------
    dict
        Static T, P, gamma, sound speed, velocity, main density, main flux,
        coolant flux.
    """
    if exact:
        t_static, p_static, k_local = _solve_exact(t0, p0, ma, rg)
        gamma = k_local
    else:
        ga = k if k is not None else 1.4
        t_static = t0 / (1.0 + (ga - 1.0) / 2.0 * ma * ma)
        p_static = p0 * (1.0 + (ga - 1.0) / 2.0 * ma * ma) ** (-ga / (ga - 1.0))
        gamma = ga

    c = math.sqrt(gamma * rg * t_static)
    v0 = ma * c
    rho = p_static / (rg * t_static)
    mass_main = rho * v0
    return {
        "static_temperature": t_static,
        "static_pressure": p_static,
        "gamma": gamma,
        "sound_speed": c,
        "velocity": v0,
        "main_density": rho,
        "main_mass_flux": mass_main,
        "coolant_mass_flux": blowing * mass_main,
    }


def _solve_exact(t0: float, p0: float, ma: float, rg: float) -> Tuple[float, float, float]:
    """Variable-gamma isentropic solve via brentq-style bisection on static T.

    Uses energy balance (cp integrated from T_static to T0 equals kinetic energy)
    and entropy balance for pressure, matching the reference exact solver.
    """
    def get_cp(t: float) -> float:
        g = _gamma(t)
        return (g * rg) / (g - 1.0)

    def energy_residual(t_static: float) -> float:
        # delta_h = int_{T_static}^{T0} cp dT
        n = 200
        t_grid = [t_static + (t0 - t_static) * i / (n - 1) for i in range(n)]
        y = [get_cp(t) for t in t_grid]
        delta_h = _trapezoid(y, t_grid)
        g_local = _gamma(t_static)
        kinetic = 0.5 * (ma**2) * g_local * rg * t_static
        return delta_h - kinetic

    lo, hi = 200.0, t0
    # bisection, robust enough for the table range
    f_lo = energy_residual(lo)
    f_hi = energy_residual(hi)
    if f_lo * f_hi > 0:
        # fall back to constant-gamma estimate
        t_static = t0 / (1.0 + 0.2 * ma * ma)
    else:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            f_mid = energy_residual(mid)
            if abs(f_mid) < 1e-6:
                lo = hi = mid
                break
            if f_lo * f_mid < 0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
            t_static = 0.5 * (lo + hi)

    # pressure via entropy: P_static = P0 * exp(- int_{T_static}^{T0} cp/T dT / Rg)
    n = 200
    t_grid = [t_static + (t0 - t_static) * i / (n - 1) for i in range(n)]
    integrand = [get_cp(t) / t for t in t_grid]
    integral = _trapezoid(integrand, t_grid)
    p_static = p0 * math.exp(-integral / rg)
    return t_static, p_static, _gamma(t_static)


# ---------------------------------------------------------------------------
# y+ / boundary-layer first-cell height (Sutherland viscosity + Schlichting Cf)
# ---------------------------------------------------------------------------
# Defaults match the reference calc script.
_MU0 = 1.7894e-5        # kg/(m s) reference viscosity at 288.15 K
_TREF = 288.15          # K
_SUTHERLAND = 110.4     # K


def sutherland_mu(t: float,
                  mu0: float = _MU0,
                  tref: float = _TREF,
                  s: float = _SUTHERLAND) -> float:
    """Dynamic viscosity by Sutherland's law at temperature T (K)."""
    return mu0 * (t / tref) ** 1.5 * (tref + s) / (t + s)


def yplus_first_cell(
    rho: float,
    velocity: float,
    length: float,
    mu: Optional[float] = None,
    t: Optional[float] = None,
    yplus: float = 1.0,
    growth: float = 1.1,
) -> dict[str, float]:
    """Compute first-cell height and boundary-layer mesh count from a y+ target.

    Uses Schlichting skin-friction correlation ``Cf = (2*log10(Re)-0.65)^-2.3``.

    Parameters
    ----------
    rho : float
        Freestream density kg/m^3.
    velocity : float
        Freestream velocity m/s.
    length : float
        Characteristic length m (e.g. porous plate length / chamber length).
    mu : float, optional
        Dynamic viscosity kg/(m s). If None, computed from ``t`` via Sutherland.
        If both ``mu`` and ``t`` are given, ``mu`` wins.
    t : float, optional
        Static temperature K, used only if ``mu`` is None.
    yplus : float
        Target y+ (1 for low-Re/omega-SST near-wall resolution).
    growth : float
        Boundary-layer growth ratio (r).

    Returns
    -------
    dict
        Reynolds, Cf, wall shear, friction velocity, first-cell center offset
        ``yp``, first-cell height ``y_one`` (= 2*yp), boundary-layer thickness,
        and number of boundary-layer cells ``N``.
    """
    if mu is None:
        if t is None:
            raise ValueError("must give mu or t so viscosity can be obtained")
        mu = sutherland_mu(t)
    if rho <= 0 or velocity <= 0 or length <= 0 or mu <= 0:
        raise ValueError("rho/velocity/length/mu must all be > 0")

    re = rho * velocity * length / mu
    cf = (2.0 * math.log10(re) - 0.65) ** -2.3
    tau_w = 0.5 * cf * rho * velocity ** 2
    u_tau = math.sqrt(tau_w / rho)
    yp = yplus * mu / rho / u_tau
    y_one = 2.0 * yp

    if re < 5.0e5:
        delta = 4.91 * length / re ** 0.5
    else:
        delta = 0.38 * length / re ** 0.2

    # boundary-layer cell count, r != 1
    if growth == 1.0:
        n = int(math.ceil(delta / y_one))
    else:
        n = int(math.ceil(math.log(1.0 - delta * (1.0 - growth) / y_one) / math.log(growth)))
    y_final = y_one * growth ** (max(n - 1, 0))

    return {
        "reynolds": re,
        "cf": cf,
        "wall_shear": tau_w,
        "friction_velocity": u_tau,
        "yp": yp,
        "y_one": y_one,
        "delta": delta,
        "n_cells": n,
        "y_final": y_final,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt(v: float, width: int = 12) -> str:
    return f"{v:>{width}.4e}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Fluent pre-processing calculators")
    p.add_argument("--porous", action="store_true", help="compute porous resistance")
    p.add_argument("--dp", type=float, default=1e-4, help="mean particle diameter, m")
    p.add_argument("--eps", type=float, default=0.3, help="porosity")
    p.add_argument("--isentropic", action="store_true", help="compute isentropic flow")
    p.add_argument("--ma", type=float, default=2.0, help="Mach number")
    p.add_argument("--t0", type=float, default=300.0, help="total temperature, K")
    p.add_argument("--p0", type=float, default=101325.0, help="total pressure, Pa")
    p.add_argument("--k", type=float, default=None, help="gamma (default 1.4)")
    p.add_argument("--exact", action="store_true", help="variable-gamma exact solve")
    p.add_argument("--blowing", type=float, default=0.02, help="blowing ratio F")
    p.add_argument("--area", type=float, default=None,
                   help="main inlet area (m^2) for mass-flow rate of coolant at 100%% F (=area*flux)")
    p.add_argument("--yplus", action="store_true", help="compute boundary-layer first-cell height")
    p.add_argument("--rho", type=float, default=None, help="freestream density kg/m^3 (for --yplus)")
    p.add_argument("--v", type=float, default=None, help="freestream velocity m/s (for --yplus)")
    p.add_argument("--length", type=float, default=0.00025, help="char. length m (for --yplus)")
    p.add_argument("--mu", type=float, default=None, help="dynamic viscosity kg/(m s) (for --yplus)")
    p.add_argument("--gas-temp", type=float, default=None,
                   help="static T K for Sutherland viscosity if --mu not given")
    p.add_argument("--yplus-target", type=float, default=1.0, help="target y+ (default 1)")
    p.add_argument("--growth", type=float, default=1.1, help="boundary-layer growth ratio")
    args = p.parse_args(list(argv) if argv else None)

    if args.porous:
        r = porous_resistance(args.dp, args.eps)
        print("=== Porous medium (dp=%.3g m, eps=%.3g) ===" % (args.dp, args.eps))
        print("  permeability  K          = %s m^2" % _fmt(r["k"]))
        print("  viscous resistance 1/K   = %s 1/m^2" % _fmt(r["viscous_resistance"]))
        print("  inertial resistance C2   = %s 1/m (USE THIS)" % _fmt(r["inertial_resistance"]))
        print("  [ref] F = %.5f" % r["f"])
        print("  [ref] F/sqrt(K) = %s (do NOT use)" % _fmt(r["c2_f_over_sqrtk"]))

    if args.isentropic:
        r = solve_isentropic(
            args.ma, args.t0, args.p0,
            k=args.k, exact=args.exact, rg=Rg_AIR, blowing=args.blowing,
        )
        print("=== Isentropic flow (Ma=%.3g, T0=%.3g K, P0=%.3g Pa)%s ===" % (
            args.ma, args.t0, args.p0, ", exact" if args.exact else ""))
        print("  static temperature       = %s K" % _fmt(r["static_temperature"]))
        print("  static pressure          = %s Pa" % _fmt(r["static_pressure"]))
        print("  gamma                    = %.4f" % r["gamma"])
        print("  sound speed              = %s m/s" % _fmt(r["sound_speed"]))
        print("  velocity v0              = %s m/s" % _fmt(r["velocity"]))
        print("  main density             = %s kg/m^3" % _fmt(r["main_density"]))
        print("  main mass flux           = %s kg/(m^2 s)" % _fmt(r["main_mass_flux"]))
        print("  coolant mass flux        = %s kg/(m^2 s) (F=%.4g)" % (
            _fmt(r["coolant_mass_flux"]), args.blowing))
        if args.area:
            main_mdot = r["main_mass_flux"] * args.area
            cool_mdot = main_mdot * args.blowing
            print("  [area-based] main mass flow = %.6g kg/s" % main_mdot)
            print("  [area-based] coolant mass flow = %.6g kg/s" % cool_mdot)

    if args.yplus:
        if args.rho is None or args.v is None:
            print("ERROR: --yplus requires --rho and --v.", file=sys.stderr)
            p.print_help()
            return 1
        r = yplus_first_cell(
            rho=args.rho, velocity=args.v, length=args.length,
            mu=args.mu, t=args.gas_temp,
            yplus=args.yplus_target, growth=args.growth,
        )
        mu_eff = args.mu if args.mu is not None else sutherland_mu(args.gas_temp)
        print("=== y+ / boundary-layer (rho=%.4g, v=%.4g, L=%.4g m, mu=%.4g, y+=%.3g) ===" % (
            args.rho, args.v, args.length, mu_eff, args.yplus_target))
        print("  Reynolds  Re        = %.4g" % r["reynolds"])
        print("  Cf (Schlichting)     = %.6f" % r["cf"])
        print("  wall shear tau_w     = %s Pa" % _fmt(r["wall_shear"]))
        print("  friction velocity    = %s m/s" % _fmt(r["friction_velocity"]))
        print("  first-cell center yp = %s m" % _fmt(r["yp"]))
        print("  first-cell height    = %s m (USE THIS)" % _fmt(r["y_one"]))
        print("  BL thickness delta   = %s m" % _fmt(r["delta"]))
        print("  number of BL cells   = %d" % r["n_cells"])
        print("  final cell thickness = %s m (growth ratio %.3f)" % (
            _fmt(r["y_final"]), args.growth))

    if not args.porous and not args.isentropic and not args.yplus:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
