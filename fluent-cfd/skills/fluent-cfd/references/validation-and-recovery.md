# Validation & Error Recovery

Use before claiming a Fluent result is usable, and when Fluent fails to launch, diverges, or produces suspicious output.

## Setup integrity

- Units and dimensions correct; materials/property models match the regime; BCs match known physical inputs; reference values set for coefficients; mesh zones/interfaces match the geometry and physics.

## Mesh quality

- Skewness, orthogonal quality, aspect ratio, non-orthogonality acceptable for the solver/model.
- Boundary-layer mesh supports the wall treatment and y+ target; important gradients have local resolution.
- A mesh-independence plan exists for final results.

## Conservation

- Net mass imbalance checked and reported; energy imbalance checked when energy is active; phase conservation checked for multiphase; forces/fluxes/source terms consistent in sign and magnitude.

## Convergence & monitoring

- Residuals are only one piece of evidence. Objective monitors must stabilize or reach periodic/statistical stationarity.
- Key fields show physically plausible distributions; warnings explained or resolved.

## Result review

- Compare against an estimate, experiment, literature, previous simulation, or simplified calculation when possible.
- Check sensitivity to mesh, time step, turbulence model, boundary assumptions for final claims.
- Report uncertainty and unresolved risks instead of overstating precision.

## Minimum acceptance statement

- "Runnable": setup starts and smoke run is stable.
- "Numerically converged": residuals, monitors, and balances meet criteria.
- "Physically validated": result has comparison evidence or sensitivity checks.
- "Not trusted": list the blocking issue and next correction.

## Recovery — launch / license failure

- Run `server_info`; inspect PyFluent version, Ansys roots (`AWP_ROOT252`), active session state.
- Check Fluent is installed and the version matches PyFluent; check license availability before retrying repeated launches; close stale sessions.

## Recovery — divergence / floating-point exception

- Stop long iteration sequences. Check mesh quality, negative volumes, poor skewness, boundary placement.
- Revisit BCs, units, material properties, operating pressure; reinitialize from a physically plausible state.
- Reduce time step / under-relaxation appropriately; start with a short stable run before restoring higher-order numerics.

## Recovery — reversed flow at outlet

- Determine whether backflow is physical or outlet-placement driven; move outlet farther downstream if recirculation crosses it; define meaningful backflow values; avoid outflow boundaries in recirculating cases.

## Recovery — negative volume / mesh failure

- Do not attempt solver fixes before fixing mesh defects; inspect local cells/interfaces/dynamic-mesh settings/moving boundaries; regenerate/repair the mesh.

## Recovery — CFL / transient instability

- Reduce time step; check velocity scales, mesh size, rotation speed, acoustic speed, interface motion; confirm temporal resolution matches the physics being measured.

## Recovery — residual stagnation

- Check whether monitors are stable (stagnation is not always failure). If monitors drift, review numerics, BCs, mesh quality, model stiffness. Check conservation balances before declaring convergence.

## Recovery rule

Make one small, explainable change at a time, then run a short smoke test. Do not stack multiple unverified changes and then attribute success to one of them.
