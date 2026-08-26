#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fluent_host.py - launches a Fluent GUI session and holds it, then drives the
iteration OUTSIDE any run_code timeout, as the "host" half of a two-process
handoff. The agent attaches via MCP to this session for interactive setup and
read-only monitoring; JSON files are the control channel.

Per operation from a single process; the host never runs a long iterate inside a
run_code call (that would be killed by the per-call timeout).

Use:
  host (this script, as a background job):
    python fluent_host.py --case-dir <dir> [--version ...] [--no-gui] [--keep-open]
  then the agent:
    * attach:   mcp connect ip/port/password from <dir>/session_info.json
    * setup:    read case, set params, init, monitors (short calls)
    * hand off: write <dir>/go.json                    {blocks, iters_per_block, stop_residual, ...}
    * monitor:  read <dir>/run_status.json (each block) + short get_state
    * control:  write <dir>/control.json between blocks {action, add_blocks, iters_per_block, stop_residual}
"""
import sys, os, json, time, io, glob, re, argparse, contextlib, traceback


def dprint(*a):
    print(*a); sys.stdout.flush()


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _get_conn(launch_ts):
    """Read ip/port/password from the newest serverinfo file created by launch."""
    out = dict(ip=None, port=None, password=None)
    dirs = [os.environ.get("TEMP"), os.environ.get("TMP"), "C:\\Windows\\Temp", "/tmp"]
    cands = []
    for d in dirs:
        if d and os.path.isdir(d):
            try:
                for f in glob.glob(os.path.join(d, "serverinfo*")):
                    if os.path.getmtime(f) >= launch_ts - 60:
                        cands.append(f)
            except Exception:
                pass
    if not cands:
        return out
    newest = max(cands, key=os.path.getmtime)
    try:
        lines = [l.strip() for l in open(newest, encoding="utf-8", errors="ignore") if l.strip()]
        hp = lines[0].rsplit(":", 1)
        out["ip"] = hp[0]
        out["port"] = hp[1] if len(hp) > 1 else None
        out["password"] = lines[1] if len(lines) > 1 else None
    except Exception:
        pass
    return out


_ROW = re.compile(r"^\s*(\d{1,5})\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)\s+([0-9eE.+-]+)")
def _last_residual(text):
    last = None
    for ln in (text or "").splitlines():
        m = _ROW.match(ln)
        if m:
            last = dict(iter=m.group(1), continuity=m.group(2), x_velocity=m.group(3),
                        y_velocity=m.group(4), energy=m.group(5), k=m.group(6), omega=m.group(7))
    return last


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case-dir", default=".")
    p.add_argument("--session-info", default="session_info.json")
    p.add_argument("--go", default="go.json")
    p.add_argument("--control", default="control.json")
    p.add_argument("--status", default="run_status.json")
    p.add_argument("--snap-dir", default="snaps")
    p.add_argument("--final", default="tc-39-F002-final.cas.h5")
    p.add_argument("--proc", type=int, default=16)
    p.add_argument("--no-gui", action="store_true")
    p.add_argument("--version", default=None)
    p.add_argument("--keep-open", action="store_true")
    p.add_argument("--poll", type=float, default=2.0)
    a = p.parse_args()

    cd = a.case_dir
    os.makedirs(cd, exist_ok=True)
    session_info = os.path.join(cd, a.session_info)
    go_path = os.path.join(cd, a.go)
    control_path = os.path.join(cd, a.control)
    status_path = os.path.join(cd, a.status)
    snapdir = os.path.join(cd, a.snap_dir)
    os.makedirs(snapdir, exist_ok=True)
    final = os.path.join(cd, a.final)

    launch_ts = time.time()
    solver = None
    try:
        import ansys.fluent.core as pyfluent
        launch_kwargs = dict(dimension=2, processor_count=a.proc, cleanup_on_exit=(not a.keep_open))
        if a.version:
            launch_kwargs["product_version"] = a.version
        if not a.no_gui:
            launch_kwargs["ui_mode"] = "gui"
        dprint("launching fluent (dim=2 proc=%s ui=%s) ..." % (a.proc, "gui" if not a.no_gui else "no_gui"))
        solver = pyfluent.launch_fluent(**launch_kwargs)

        conn = _get_conn(launch_ts)
        info = dict(ip=conn["ip"], port=conn["port"], password=conn["password"],
                    pid=os.getpid(), start_time=time.strftime("%Y-%m-%d %H:%M:%S"))
        write_json(session_info, info)
        dprint("session_info.json: %s" % json.dumps(info))

        # idle until go.json (agent does interactive setup via MCP first)
        dprint("HOST idle; waiting for %s ..." % go_path)
        while not os.path.exists(go_path):
            time.sleep(a.poll)
            if os.path.exists(control_path):
                c = read_json(control_path)
                if c and c.get("action") == "abort":
                    dprint("HOST abort requested before setup; exiting."); return

        go = read_json(go_path) or {}
        blocks = int(go.get("blocks", 60))
        itpb = int(go.get("iters_per_block", 500))
        stop_res = float(go.get("stop_residual", 1e-4))
        consec = int(go.get("consec", 3))
        dprint("go.json: blocks=%d iters_per_block=%d stop_residual=%g" % (blocks, itpb, stop_res))

        below, done, b = 0, False, 1
        res = None
        while not done and b <= blocks:
            ctl = read_json(control_path)
            if ctl:
                act = ctl.get("action")
                if act == "stop":
                    dprint("control: stop -> finishing"); done = True; break
                if act == "converge":
                    stop_res = float(ctl.get("stop_residual", stop_res))
                    consec = int(ctl.get("consec", consec))
                if "add_blocks" in ctl: blocks += int(ctl["add_blocks"])
                if "iters_per_block" in ctl: itpb = int(ctl["iters_per_block"])
                if "stop_residual" in ctl: stop_res = float(ctl["stop_residual"])
                write_json(control_path, {"handled": True, "at": time.time()})

            dprint("=== block %d/%d: iterate %d ===" % (b, blocks, itpb))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                solver.tui.solve.iterate(str(itpb))
            out = buf.getvalue()
            res = _last_residual(out)

            total = b * itpb
            snap = os.path.join(snapdir, "tc39_%d.dat.h5" % total)
            solver.tui.file.write_data(snap)

            status = dict(state="running", block=b, blocks_total=blocks, total_iters=total,
                          residual=res, last_snapshot=snap, control=read_json(control_path))
            write_json(status_path, status)

            if res and re.search(r"^[0-9.eE+-]+$", str(res["continuity"])):
                below = below + 1 if float(res["continuity"]) < stop_res else 0
            if below >= consec:
                write_json(status_path, dict(status, state="converged",
                                             stop_reason="continuity < %g for %d blocks" % (stop_res, consec)))
                dprint("converged."); done = True; break
            b += 1

        dprint("writing final case+data ...")
        solver.tui.file.write_case_data(final)
        write_json(status_path, dict(read_json(status_path) or {}, state="done", final=final,
                                     end=time.strftime("%Y-%m-%d %H:%M:%S")))
        dprint("RUN COMPLETE.")
    except Exception as e:
        dprint("HOST ERROR:\n%s" % "".join(traceback.format_exception(e)))
        write_json(status_path, dict(state="error", error="".join(traceback.format_exception(e))))
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


if __name__ == "__main__":
    main()
