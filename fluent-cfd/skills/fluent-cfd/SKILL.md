---
name: fluent-cfd
description: Workflow and judgment layer for ANSYS Fluent / PyFluent CFD simulations driven through the local `ansys-fluent-mcp` MCP server. Use when driving a Fluent solver session, mesh quality, boundary conditions, turbulence models, residual convergence, post-processing, solver diagnostics, or validation of Fluent results. Execution goes through the `mcp__fluent__*` tools; this skill decides the order of operations, checks, and validation criteria.
---

# Fluent CFD

Use this skill as the workflow and judgment layer for Ansys Fluent work. Keep Fluent documentation as the fact source, use the local `ansys-fluent-mcp` server as the execution layer, and use this skill to decide the order of operations, checks, and validation criteria.

## Operating rules

- Define the physics BEFORE touching the solver: objective quantity, geometry, units, fluid(s), regime, compressibility, heat transfer, multiphase, rotating/moving zones, and expected validation evidence.
- Residual decrease alone is NOT convergence. Require monitor stabilization and conservation checks for the quantities that matter.
- Do not skip mesh quality, units, boundary-zone naming, boundary-condition consistency, or wall-resolution checks.
- Do not change turbulence models without a physical reason or a stated validation purpose.
- Before starting Fluent or consuming a license, state that the action will launch Fluent and may occupy a license/session; end live sessions with `disconnect` when done (keep it open only if the user asks — use `--keep-open` for the GUI long-run script).
- Show the user the generated PyFluent code before `run_code`, and run `validate_code` first for safety-critical operations. The server rejects `.tui.*` calls — use `solver.settings.*`.

## Workflow

1. Frame the case: objective metrics, physics, known inputs, missing data, expected outputs, acceptance criteria.
2. Choose solver and models: pressure-based vs density-based, steady vs transient, energy, multiphase, turbulence, wall treatment, reference values (`workflow.md`).
3. Check the mesh and setup basis: units, cell/face zones, boundary names, quality metrics, non-orthogonality/skewness, y+ target.
4. Set/review materials, BCs, operating/reference conditions, numerics, initialization, monitors.
5. Run a smoke test first: a short iteration/time-step run to catch setup errors before a full solve.
6. Iterate while monitoring residuals, integral balances, and objective quantities.
7. Save case/data and report validation status, remaining risks, and next checks.

## Execution loop (through `mcp__fluent__*`)

1. `session_status` — say so if Fluent will launch / consume a license.
2. `connect` (launch/attach). If the case is 2D, connect with `dimension: 2`.
3. `run_code("solver.settings.file.read_case_data(file_name=r'<path>')")` loads case+data.
4. Discover with `get_state` / `list_named_objects` / `find_api` / `get_help`.
5. `run_code` a SHORT smoke `iterate`; verify with `solver_status` / `simulation_report`.
6. Continue only when stable. **Anything longer than a smoke run must go through the host + MCP-attach workflow** (`scripts/fluent_host.py`), or `solver_loop.py` / `long_run.journal` as fallbacks — a per-call timeout kills a `run_code`-driven long iteration and its session. See `references/host-attach-run.md`.
7. `run_code` `write_case`/`write_data` to preserve state; `disconnect` when done.

Golden rules (details in `pyfluent-execution.md`): `get_state`/`find_api` take a STRING, not a list; named expressions need units (`'288.15 [K]'`); discretization schemes are a named collection (`ds["k"]=...`); never retry a `risk_blocked` snippet; on any tool error STOP and propose the smallest safe recovery.

## References

Load only what the task needs:

- `references/workflow.md` — end-to-end order + solver/model selection.
- `references/boundaries-and-turbulence.md` — boundary types + turbulence/wall treatment / y+.
- `references/numerics-and-convergence.md` — numerics, initialization, monitors, convergence (incl. reacting/shock-flow judgment).
- `references/pyfluent-execution.md` — the `ansys-fluent-mcp` tool surface, safe call order, all verified pitfalls (launch/dimension, field data, console capture, sandbox limits, reacting gotchas), and long-run execution. **Read this before real execution.**
- `references/host-attach-run.md` — the recommended **long-run workflow**: `scripts/fluent_host.py` launches + holds a session, the agent attaches via MCP (`connect ip/port/password` from `session_info.json`) for interactive setup, then drives iteration block-by-block with `go.json`/`run_status.json`/`control.json` and read-only monitoring.
- `references/preprocessing-calculations.md` — porous-medium resistance (Ergun/Forchheimer, corrected C2), isentropic flow, y+/boundary-layer first-cell height, validated gas properties. Run `scripts/preprocessing.py` before setting BCs / porous zones / BL mesh.
- `references/validation-and-recovery.md` — conservation, mesh independence, plausibility, acceptance statements, and launch/divergence/CFL/negative-volume recovery.

## Safe-by-construction

On any tool error, stop the sequence, summarize the failure, read `validation-and-recovery.md` if relevant, and propose the smallest safe recovery — do not retry the same snippet blindly.
