# PyFluent Execution (ansys-fluent-mcp)

The only way to actually drive Fluent is through the local `ansys-fluent-mcp`
server (`mcp__fluent__*`). Everything below was verified live on Fluent 2025 R2 /
PyFluent 0.41; use it to skip exploratory probing and reach the answer in <=2
round trips per intent.

## Tool surface (registered `mcp__fluent__*`)

- `session_status` / `solver_status`: connection + backend state; is it iterating.
- `connect(...)`: launch a local Fluent session or attach to a running one — **may consume a license, say so first**. Launch dimension/cores go here (`connect_kwargs={"dimension": 2, "processor_count": N}`).
- `disconnect`: tear the session down. End live sessions when done (unless the user wants to keep it open).
- `find_api`, `get_help`, `get_state(path)`, `get_targeted_context`, `list_named_objects`, `find_named_object`, `select_named_objects`, `summarize_setup`, `simulation_report`: discover/read.
- `run_code(code)`: the ONLY mutator — executes a sandboxed PyFluent snippet.
- `validate_code(code)`: AST + signature check, no execution. Run before safety-critical `run_code`.
- `mesh_quality(include_check?)`, `list_fields(scope?)`, `compare_files(a,b)`, `screenshot(...)`: routed intents.

There is **no** `launch_fluent` / `read_case` / `run_tui` / `iterate` / `write_case_data` / `exit_fluent` tool. Do not call them on this server.

## Golden rules / code discipline

- **Never emit `.tui.*`** from `run_code`; use `solver.settings.*` / `solver.<root>.<path>...`. `setup.solution.*` does not exist. Path roots: `setup.` | `solution.` | `results.` | `file.` | `mesh.`.
- `get_state` / `find_api` take a **STRING** path, not a list. `.list()`/`.list_properties()` are void (print only).
- Named expressions REQUIRE units when dimensional (`'288.15 [K]'`, `'1.225 [kg/m^3]'`). Bare numbers break report defs / BC values.
- Show the user the generated code before `run_code`; there is no undo. Keep snippets small, explicit, auditable. Prefer new filenames over overwriting archives.
- **Discretization scheme is a named collection**: `spatial_discretization.discretization_scheme["k"] = "first-order-upwind"`, NOT `ds.k = ...` (raises `AttributeError`).

## Safe call order

1. `session_status`; tell the user if Fluent will launch / consume a license.
2. `connect` — **ATTACH ONLY**: pass `ip`/`port`/`password` (from `session_info.json`). Do NOT call `connect` to LAUNCH a new Fluent session (no ip/port spawns a session tied to the `run_code` lifecycle); use `scripts/fluent_host.py` to launch+hold, then attach. See `host-attach-run.md`.
3. `run_code("solver.settings.file.read_case_data(file_name=r'<path>')")` loads case+data in one shot (`read_case` = case only; `file.read_data` = data only).
4. Discover with `get_state` / `list_named_objects` / `find_api` / `get_help`.
5. `run_code("solver.solution.run_calculation.iterate(iter_count=N)")` — SHORT smoke run only.
6. Inspect `solver_status`, `simulation_report`, warnings, outputs.
7. Continue only after the smoke run is stable (see the long-run section for anything longer).
8. `run_code("solver.file.write_case(...)")` / `write_data` to preserve state.
9. `disconnect` unless the user wants the session kept open.

## Launch & dimension fixes (each cost a round trip if missed)

- **`File has wrong dimensions (2)`** at case read ⇒ the CASE is 2D but the session is 3D. Fix the launch, do NOT investigate further. Use `dimension=2`.
- In **standalone PyFluent** (`solver_loop.py`) the launch is:
  ```python
  launch_fluent(product_version="25.2.0", dimension=2, processor_count=16, ui_mode="gui")
  ```
  - Use **`product_version=`** NOT the deprecated `version=` — `version=` silently ignores `dimension=2` and launches 3D.
  - **GUI** = `ui_mode="gui"` (real window). **Headless** = OMIT `ui_mode` (→`-hidden`, verified). Do NOT use `ui_mode="no_gui"` → `-gu -driver null` **hangs** in a background job.
- Verify cores from the OS side: `Get-Process fl_mpi*` count == requested cores.
- After any scale/init, verify by pulling real field values back out (§ Field data) — uniform values prove the field was set.

## Field data (do NOT trust `list_fields` / `solver_status.initialized`)

In this build `list_fields` returns `[]` and `solver_status.initialized=false` even when data is loaded. Decisive checks:

```python
solver.fields.field_data.is_data_valid()      # True = solution data loaded

from ansys.fluent.core.fields.field_data_interfaces import ScalarFieldDataRequest
req = ScalarFieldDataRequest(field_name="temperature", surfaces=["outlet"])
r = solver.fields.field_data.get_field_data(req)
vals = r["outlet"]                              # numpy ndarray directly; no .values wrapper
f = [float(v) for v in list(vals)]              # pure-python min/max/mean
```

- `LiveFieldData` has NO `get_scalar_field_data` (old API). Use request objects.
- **Do NOT use `solver.fields.reduction.area_average(...)`** in 2D species cases: it deterministically prints red console errors (`api-checks-before-command-or-query ... temp_expr_1/get-value`) and never returns. Compute averages from raw field data, or use a report definition.
- `Mesh coordinates`: `SurfaceFieldDataRequest(..., data_types=[SurfaceDataType.Vertices])` — face zones raise `NotImplementedError`; for bounding boxes use Console capture.

## Console capture (the ONLY reliable way to read TUI output)

`mesh.check()` / `size_info()` / `quality()` return `None`; their output arrives asynchronously on the transcript stream.

```python
captured = []
def sink(msg): captured.append(str(msg))
solver.transcript.register_callback(sink)
solver.transcript.start()
# ... trigger command(s) ...
for _ in range(5):                              # burn gRPC round trips; pushes are async
    solver.settings.setup.models.viscous.get_state()
solver.transcript.stop()
print([l.strip() for l in captured if l.strip()])
```

Without the burn loop you capture 0 lines. `Domain Extents:` also comes from this route. `solver.scheme_eval` is an OBJECT: `solver.scheme_eval.eval("(expr)")` / `.string_eval("%sym")` (calling it directly raises `TypeError`).

## run_code sandbox limits (each violation costs a round trip)

- Import allow-list **BLOCKS** `time`, `numpy`, `inspect`. Allowed: `ansys.fluent.core.*`. Need a delay? Burn round trips (§ Console capture), never `sleep`.
- Forbidden call patterns: `hasattr(x, "__getitem__")`, dunder probing. Use try/except.
- Keep snippets pure-python + settings API; compute stats with plain loops.

## Reacting / species gotchas

- Reaction stoichiometry (e.g. a `reaction-1` coefficient) is **not exposed** anywhere in the settings tree (probe `setup.models.species.reactions` / `materials.mixture[...].reactions` = option-only; `find_api`/probe miss it). It can only be changed via a journal/TUI line or the original chemistry source — a settings-API edit is not possible.
- Fluent emits `Warning: mass imbalance in reaction-1 stoichiometry.` for a mass-imbalanced global pyrolysis reaction. This is non-fatal, but the balance is what it is.

## Long-run execution (NEVER long-block-iterate via `run_code`)

Running `iterate(N)` for a long N blocks the call; if it outlasts the client per-call timeout (`toolCallTimeoutMs`, fluent = **180000** in `agent.cordis.yml`, applied by `packages/mcp/mcp-client/src/tools.ts:92`) the harness aborts and the MCP backend kills the Fluent session → mid-run state is lost. Raising the timeout only postpones it (any finite timeout is eventually exceeded).

**Therefore: run long iterations in a process NOT owned by any `run_code` request.**

- `scripts/solver_loop.py` (PyFluent): launches its own session, iterates in blocks, saves `snaps\*.dat.h5`, writes a JSON progress report. Launch as a background job; no tool-call timeout can interrupt it.
  - Default GUI visible; `--no-gui` = headless (`-hidden`). `--keep-open` leaves the GUI/session open after the run (close manually); `cleanup_on_exit=False` + skip `solver.exit()`.
  - `--blocks N --iters-per-block M`; auto-stop when continuity < `--stop-residual` for `--consec` blocks.
- `scripts/long_run.journal` (plain GUI Fluent): `fluent.exe 2ddp -t16 -i long_run.journal`; Fluent iterates itself, snapshots each block. Env vars `FLUENT_CASE_DIR/FLUENT_CASE/FLUENT_SNAP_DIR/FLUENT_OUT/FLUENT_BLOCKS/FLUENT_ITERS` set paths/counts.
- `run_code` is for SHORT reads/setup/smoke only.

## Failure handling

- `risk_blocked`: read the stderr suggestion, rewrite the snippet, re-submit — do NOT retry the same snippet.
- `sequence_error` (use-before-create): reorder (define first, then reference) and re-submit.
- `solver_disconnected`: `connect` again, reload case/data, re-issue.
- Launch/license: check Ansys root (`AWP_ROOT252`), product version, license availability; close stale sessions before retrying.
- On any tool error: STOP, summarize the failure, and propose the smallest safe recovery.
