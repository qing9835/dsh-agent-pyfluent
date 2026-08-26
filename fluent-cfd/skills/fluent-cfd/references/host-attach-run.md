# Host + MCP-attach long-run workflow

> ⚠️ **NEVER call `connect` to LAUNCH Fluent.** `connect` without `ip`/`port` spawns a
> NEW session tied to the `run_code` lifecycle (dies on timeout). Launch+hold is the
> host's job (`scripts/fluent_host.py`); the agent only ATTACHES via `connect(ip, port, password)`.

This is the recommended way to run a **long** simulation. The iteration runs in a
separate **host process** (immune to the `run_code` per-call timeout), while the
agent drives interactive setup and read-only monitoring through MCP. Use this for
anything beyond a short smoke run.

> Why: `mcp__fluent__run_code` blocks until a snippet finishes; if it outlasts the
> client per-call timeout (`toolCallTimeoutMs`, fluent = 180000 in `agent.cordis.yml`)
> the harness aborts and the MCP backend kills the session. So the long iterate lives
> in the host process, not in a `run_code` call. (See `pyfluent-execution.md` § Long-run.)

## Architecture (two-process handoff)

```
HOST (long-lived background job, timeout-immune)          MCP (agent)
  launch_fluent(gui) --write session_info.json----->
  [idle, waiting for go.json] <---- read session_info
      ^                                        attach(ip,port,password)
      |                                        interactive setup (read case /
      |                                        set params / init / monitors)
      |   <------ write go.json ----            (short calls, <180s each)
  read go.json -> block-iterate
      |   each block: snapshot + run_status.json --->  read-only monitor
      |   at block start: read control.json  <----   write control.json
      |   (continue / add N / stop / converge)
  on stop/converge: write final case+data -->     postprocess (simulation_report /
  (--keep-open keeps the GUI open)                 field data / screenshot)
```

## JSON control channel (all in the case-dir)

| file | written by | fields |
|---|---|---|
| `session_info.json` | host | `{ip, port, password, pid, start_time}` — MCP attach creds |
| `go.json` | agent (after setup) | `{blocks, iters_per_block, stop_residual, consec}` — **steps not hard-coded** |
| `run_status.json` | host (each block) | `{state, block, blocks_total, total_iters, residual, last_snapshot, control, final}` |
| `control.json` | agent (between blocks) | `{action, add_blocks, iters_per_block, stop_residual, consec}` — takes effect at the **next block boundary** |

`control.json` `action`: `"continue"` (default), `"add_blocks": N`, `"stop"`,
`"converge"` (tighten `stop_residual`/`consec`), or `"abort"` (before setup).
It may also carry `iters_per_block` / `stop_residual` / `consec` updates.

## Host script

`scripts/fluent_host.py` (launch as a DSH background job; default GUI visible):

```
python scripts/fluent_host.py --case-dir <dir> [--no-gui] [--keep-open] [--version ...]
```

- Writes `session_info.json`, then idles until `go.json` appears.
- Reads `go.json`, then block-iterates: `iterate(iters_per_block)`, writes a snapshot
  `snaps\tc39_<total>.dat.h5` and `run_status.json`.
- At the start of each block it reads `control.json` and applies any directives.
- On stop/converge writes the final case+data; `--keep-open` leaves the GUI open.

## Agent recipe (MCP side)

1. `session_status`; tell the user Fluent will launch / consume a license.
2. Start `fluent_host.py` as a background job; wait for `session_info.json`.
3. `connect` with the extracted `ip`/`port`/`password` (attach). Verify with
   `session_status` / a short `get_state` (empty session => `boundary_conditions.inactive`).
4. Interactive setup (all SHORT calls): `run_code` to read the case, set/adjust
   parameters, initialize, and set monitors/report definitions.
5. Write `go.json` (blocks, iters_per_block, stop_residual, consec). `run_code` is
   done after this — do NOT iterate via `run_code`.
6. Monitor read-only by reading `run_status.json` (and optional short `get_state`).
   After each block, report residual/progress to the user and wait for instruction.
7. Per instruction, write `control.json` (continue / add_blocks / stop / converge).
8. On stop/converge, `run_code` post-processing on the final case+data:
   `simulation_report`, field data (`ScalarFieldDataRequest`), or `screenshot`.

## Convergence judgment

- Do not rely on residuals alone. For strong-shock + multi-species reacting flows
  `continuity`/`omega` plateau and the history is **non-monotonic** (see
  `numerics-and-convergence.md`). Judge by monitor physics (wall temperature, species
  yields, coolant fraction, pressure loss) plus a stable `run_status.json` state.
- `go.json`/`control.json` let you tune `stop_residual`/`consec` at block boundaries
  without restarting.

## Failure recovery

- **Attach fails (`connect` error)**: confirm `session_info.json` has real values
  (ip/port/password). If null, the host could not read the serverinfo file — relaunch
  the host and retry. Check the host log; the session must be alive.
- **Host stuck (no new `run_status.json`)**: check the host job output / `.trn` for
  an error; write `control.json {"action":"stop"}` (or `abort`) then kill the job.
- **Orphaned processes**: killed sessions can leave `hydra_pmi_proxy` orphans locking
  `.trn` files. Terminate them (`Get-Process hydra_pmi_proxy | Stop-Process -Force`)
  to release the files / license.
- **`solver_disconnected` in MCP**: reconnect (`connect` with the same creds) and,
  if needed, re-read the case/data.

## Notes

- The MCP `connect(ip, port, password)` attaches to the host session; the host holds
  the Fluent process. Two clients briefly touch it (host + MCP) — this is safe because
  the MCP disconnects (or is idle) while the host drives the iteration.
- `run_code` must remain short; long iteration belongs to the host.
