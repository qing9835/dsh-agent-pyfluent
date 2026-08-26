# Numerics & Convergence

Use for solver controls, initialization, monitors, and convergence assessment.

## Numerics

- Start with stable lower-order/default schemes only when needed for robustness; move to higher-order for final engineering results when stable.
- Choose pressure-velocity scheme appropriate to flow stiffness/compressibility/convergence behavior.
- Adjust under-relaxation factors only with a reason: oscillation, divergence, stiffness, slow coupling.
- Transient: choose time step from physical time scales, Courant number, rotating speed, wave speed, desired temporal resolution.
- **Discretization scheme is a named collection**: `spatial_discretization.discretization_scheme["k"] = "first-order-upwind"` (NOT `ds.k = ...`).

## Initialization

- Initialize from physically meaningful zones or hybrid initialization.
- Patch fields for multiphase, temperature gradients, rotating regions, known recirculation.
- Run a short smoke test before a long solve. `compute_defaults()` without arguments uses the FIRST inlet (may be the wrong one) — always pass explicit `from_zone_type`/`from_zone_name`.

## Convergence evidence (more than residuals)

- Residuals decrease and level at acceptable values for the model.
- Target monitors stabilize: force, pressure drop, heat rate, mass flow, averaged temperature, torque, phase volume.
- Mass imbalance small relative to total flow; energy imbalance checked when energy is active.
- Key contours and vectors physically plausible.
- No unresolved warnings dominate: reversed flow, clipped variables, FP exceptions, poor-quality cells, boundedness issues.

## Reacting / shock-flow convergence (hard-won)

- Strong-shock + multi-species reaction cases have **`continuity` and `omega` as the slow residuals**, and the history is **non-monotonic** (e.g. drops in the first ~50 iters, then rises/re-oscillates as the shock/chemistry field develops). Do not read a single residual sample as a trend.
- Do not expect a low residual floor (e.g. 1e-4) with first-order + strong shock; **judge by monitor physics quantities** (wall temperature, species yields, coolant fraction, total-pressure loss) rather than raw residuals.
- Iteration cost is NOT constant: early transient iterations are stiff/expensive (~tens of s/iter), then speed up as the field settles. Estimate total time from an average after ~50-100 iters, not the first few. A 2D ~1M-cell reacting case can be several s/iter → thousands of steps = many hours.
- Full runs of this size must go through `scripts/solver_loop.py` (or `long_run.journal`) — see `pyfluent-execution.md` § Long-run.

## Steady vs transient

- Steady convergence: monitor values should stop drifting, not merely oscillate around a moving mean.
- Transient convergence: require periodic/statistical stationarity or time-window convergence; residuals per time step are not the final result.

## Red flags

- Residuals stagnate while monitors drift; residuals low because equations are over-relaxed or monitors absent; long-run iteration before a smoke test; final results reported without conservation checks.
