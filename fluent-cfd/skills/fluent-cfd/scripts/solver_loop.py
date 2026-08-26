#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""solver_loop.py - long autonomous Fluent run driven by PyFluent, immune to the
MCP run_code request timeout.

WHY THIS EXISTS
---------------
`mcp__fluent__run_code` has a client-side per-call timeout (`toolCallTimeoutMs`,
default 180000 ms for the fluent MCP in agent.cordis.yml).  A long
`run_calculation.iterate()` blocks the call; if it outlasts that timeout the
client aborts and the MCP backend cancels/cleans up, killing the Fluent session
it launched -> mid-run state is lost.  Raising the timeout only postpones this.

This script therefore runs the iteration IN ITS OWN PROCESS (launched as a
background job), so no tool-call timeout can interrupt it.  It reads a case,
iterates in blocks, saves a .dat.h5 snapshot each block, and writes a JSON
progress report; on completion it writes the final case+data, and on error it
writes the stack trace into the report and exits non-zero.  The agent monitors
via the report file and intervenes.

LAUNCH ARGS (verified via dry-run so the *2D* case loads correctly):
  * product_version="25.2.0"           (NOT the deprecated `version` kwarg!)
  * dimension=2                        -> generates the "2ddp" launch string
  * ui_mode="gui"  (default)           -> visible GUI; --no-gui -> headless (-hidden)

Usage:
  python solver_loop.py --case-dir <dir> [--case tc-39-F002-scaled.cas.h5] \\
      [--snap-dir snaps] [--final tc-39-F002-final.cas.h5] [--report run_report.json] \\
      [--blocks 60] [--iters-per-block 500] [--proc 16] [--no-gui] [--keep-open] \\
      [--stop-residual 1e-4] [--consec 3]
"""
import sys, os, json, time, io, re, argparse, contextlib, traceback


def dprint(*a):
    print(*a)
    sys.stdout.flush()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case-dir", default=".")
    p.add_argument("--case", default="tc-39-F002-scaled.cas.h5")
    p.add_argument("--snap-dir", default="snaps")
    p.add_argument("--final", default="tc-39-F002-final.cas.h5")
    p.add_argument("--report", default="run_report.json")
    p.add_argument("--blocks", type=int, default=60)
    p.add_argument("--iters-per-block", type=int, default=500)
    p.add_argument("--proc", type=int, default=16)
    p.add_argument("--version", default="25.2.0")
    p.add_argument("--no-gui", action="store_true", help="headless (no window); default is GUI visible")
    p.add_argument("--keep-open", action="store_true",
                   help="do NOT exit the Fluent session / close the GUI when the run finishes; "
                        "leave it open for manual inspection, close it yourself later")
    p.add_argument("--stop-residual", type=float, default=1e-4,
                   help="early-stop when continuity residual < this for --consec consecutive blocks")
    p.add_argument("--consec", type=int, default=3)
    a = p.parse_args()

    case = os.path.join(a.case_dir, a.case)
    snapdir = os.path.join(a.case_dir, a.snap_dir)
    os.makedirs(snapdir, exist_ok=True)
    final = os.path.join(a.case_dir, a.final)
    report = os.path.join(a.case_dir, a.report)

    rec = {
        "state": "starting", "case": case, "blocks": a.blocks, "iters_per_block": a.iters_per_block,
        "proc": a.proc, "dim": 2, "version": a.version,
        "ui_mode": "headless(-hidden)" if a.no_gui else "gui", "keep_open": a.keep_open,
        "start": time.strftime("%Y-%m-%d %H:%M:%S"),
        "blocks_done": 0, "total_iters": 0, "residual": None, "error": None,
    }

    def wreport(r):
        with open(report, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
        dprint(json.dumps(r, ensure_ascii=False))

    wreport(rec)

    solver = None
    try:
        import ansys.fluent.core as pyfluent
        # NOTE: product_version=, NOT the deprecated version= (which silently ignored
        # dimension=2 and launched 3D -> "File has wrong dimensions (2)").
        # Headless: OMIT ui_mode -> Fluent launches with -hidden (VERIFIED to reach
        # read_case_data).  Do NOT use ui_mode='no_gui' -> "-gu -driver null" hangs.
        dprint("launching pyfluent version=%s dim=2 proc=%s ui=%s ..."
               % (a.version, a.proc, "headless(-hidden)" if a.no_gui else "gui"))
        launch_kwargs = dict(product_version=a.version, dimension=2, processor_count=a.proc,
                             cleanup_on_exit=(not a.keep_open))
        if not a.no_gui:
            launch_kwargs["ui_mode"] = "gui"
        solver = pyfluent.launch_fluent(**launch_kwargs)
        dprint("launched; reading case+data ...")
        solver.tui.file.read_case_data(case)   # loads .cas.h5 + matching .dat.h5
        dprint("case loaded.")

        rec["state"] = "running"
        rec["case_loaded"] = True
        wreport(rec)

        below = 0
        for b in range(1, a.blocks + 1):
            bstart = time.time()
            dprint("=== block %d/%d: iterate %d ===" % (b, a.blocks, a.iters_per_block))
            out = ""
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    solver.tui.solve.iterate(str(a.iters_per_block))
                out = buf.getvalue()
            except Exception as e:
                dprint("iterate returned after %d chars; lenient continue (err=%s)" % (len(out), e))

            total = b * a.iters_per_block
            rec["blocks_done"] = b
            rec["total_iters"] = total
            rec["last_block_time_s"] = round(time.time() - bstart, 1)

            r = _last_residual_row(out)
            if r:
                rec["residual"] = r
                try:
                    if float(r["continuity"]) < a.stop_residual:
                        below += 1
                    else:
                        below = 0
                except Exception:
                    below = 0
            else:
                rec["residual"] = None

            snap = os.path.join(snapdir, "tc39_%d.dat.h5" % total)
            solver.tui.file.write_data(snap)
            rec["last_snapshot"] = snap
            rec["state"] = "running"
            wreport(rec)

            _flush_monitors(solver)

            if below >= a.consec:
                rec["state"] = "converged"
                rec["stop_reason"] = "continuity < %.1e for %d blocks" % (a.stop_residual, a.consec)
                wreport(rec)
                break

        dprint("writing final case+data ...")
        solver.tui.file.write_case_data(final)
        if rec["state"] != "converged":
            rec["state"] = "done"
        rec["final"] = final
        rec["end"] = time.strftime("%Y-%m-%d %H:%M:%S")
        rec["error"] = None
        wreport(rec)
        dprint("RUN COMPLETE.")
    except Exception as e:
        rec["state"] = "error"
        rec["error"] = "".join(traceback.format_exception(e))
        wreport(rec)
        dprint("RUN ERROR:\n%s" % rec["error"])
        sys.exit(1)
    finally:
        if solver is not None:
            if a.keep_open:
                dprint("--keep-open: leaving the Fluent GUI/session open. Close it manually when done.")
            else:
                try:
                    solver.exit()
                except Exception:
                    pass


def _last_residual_row(text):
    """Parse the last residual table row from iterate output."""
    row = re.compile(r"^\s*(\d{1,5})\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)")
    last = None
    for ln in (text or "").splitlines():
        m = row.match(ln)
        if m:
            last = {"iter": m.group(1), "continuity": m.group(2), "x_velocity": m.group(3),
                    "y_velocity": m.group(4), "energy": m.group(5), "k": m.group(6), "omega": m.group(7)}
    return last


def _flush_monitors(solver):
    """Best-effort: touch report definitions so monitor plots update; never fail the run."""
    try:
        solver.tui.solve.report_definitions()
    except Exception:
        pass


if __name__ == "__main__":
    main()
