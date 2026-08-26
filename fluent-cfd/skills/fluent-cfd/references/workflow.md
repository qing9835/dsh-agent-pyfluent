# Workflow & Solver Selection

Keep Fluent work in a reproducible order and choose solver settings that match the physics.

## Task routing

- Planning or model choice: this file + `boundaries-and-turbulence.md` as needed.
- Case review / trust assessment: `validation-and-recovery.md`.
- Running a case: `pyfluent-execution.md` + `numerics-and-convergence.md`.
- Diagnosing failures: `validation-and-recovery.md`, then the subsystem reference.

## Minimum case definition

Capture these before recommending solver settings:

- Purpose: drag, pressure drop, heat transfer, mixing, separation, mass flow, acoustic proxy, etc.
- Regime: steady/transient, incompressible/compressible, laminar/turbulent, single/multiphase, reacting/non-reacting.
- Geometry/scale: characteristic length, boundary names, rotating/moving parts, symmetry or periodicity.
- Fluid/materials: density model, viscosity, temperature dependence, compressibility, phase properties.
- Boundary data: mass/velocity/pressure/temperature/turbulence inputs and expected outlet behavior.
- Validation evidence: experiment, analytical estimate, literature, mesh independence, conservation, or engineering target.

## Primary solver choice

- Pressure-based: default for incompressible, low-speed, and mildly compressible flows.
- Density-based: high-speed compressible flows with shocks, strong waves, or tightly coupled density-pressure dynamics.
- Steady: only when BCs and expected features are time-independent and the target quantity settles.
- Transient: vortex shedding, rotating/moving geometry, startup/shutdown, sloshing, unsteady multiphase, or any time-history objective.

## Physics toggles

- Energy: heat transfer, buoyancy with temperature variation, compressible flow, conjugate heat transfer, radiation, temperature-dependent properties.
- Gravity: buoyancy, free-surface orientation, settling, hydrostatics, density-stratified flow.
- Multiphase: require phase inventory, interface/dispersion assumption, interaction model, and expected observable before choosing VOF/mixture/Eulerian/DPM.
- Rotating machinery: MRF (steady approx) vs sliding mesh (time-resolved blade passing / transient interaction).

## Guardrails

- Do not select a more complex model just because it is available.
- Do not use steady MRF when the target is inherently unsteady.
- Do not ignore density/temperature coupling when buoyancy or compressibility drives the flow.

## Standard execution sequence

1. Confirm units and scale before assigning physics.
2. Check zones and boundary names before writing/running commands.
3. Check mesh quality and wall resolution before judging turbulence results.
4. Initialize with a physically plausible field.
5. Run a short smoke test.
6. Review residuals, warnings, reversed flow, and monitor movement.
7. Continue only when the smoke run is numerically stable (for anything longer, see `pyfluent-execution.md` § Long-run).
8. Save case/data after meaningful setup changes or a converged/accepted state.

## Reporting

End with: what was changed/checked; whether the case is runnable/converged/validated; evidence used (residuals, monitors, conservation, mesh checks, comparison target); remaining risks and the next smallest action.
