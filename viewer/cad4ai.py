"""cad4ai - local CAD tools for Claude: heavy work on this PC, a few lines of JSON back.

  cad4ai summary  M.step [--full]           parts, sizes, masses, hole patterns (text)  | --json for all
  cad4ai diff     M.step                    what changed since the previous version of this model
  cad4ai collide  M.step [--limit 0.5] [--parts A B]   all-pairs collisions / clearances (all cores)
  cad4ai holes    M.step PART               holes, patterns, shafts, planes of one part
  cad4ai dist     M.step A B                minimum distance between two parts
  cad4ai section  M.step "Z=20" [--parts ..] section areas + SVG
  cad4ai mass     M.step                    mass table (parts.json materials)
  cad4ai verify   M.step [--level 2|3] [--script S.py]   B-rep validity + collisions (+ DFM, FEM if asked)
  cad4ai after    M.step                    short report after a rebuild (diff + validity + new collisions)
  cad4ai doctor   S.py                      run a failing script, find the line, bisect fillet/chamfer
  cad4ai lint     S.py [--info]             static check before running (names, fillets, hole sizes, params)
  cad4ai new      S.py [--title ..]         script skeleton: params, assembly, export, expect(), std, cache
  cad4ai partsjson M.step                   fill in missing parts.json entries
  cad4ai report   M.step                    everything the checks know about a model (viewer Checks window)
  cad4ai variants M.step                    design variants side by side (mass, size, collisions, expect)
  cad4ai lib      candidates | accept ID | dismiss ID | new ID [title] | families   own library families
  cad4ai std      "ISO 4762 M5x16" | hole M5 | key 30 | list [--step]
  cad4ai motion   M.step [--force]          motion.json from parts.json "motion" keys (press/rotate/hinge/slide)
  cad4ai vendor   V.step                    mounting interface of a purchased part
  cad4ai fem      M.step PART --fix xmin --load "xmax=0,0,-100" [--material al] [--elements 60000]
  cad4ai dfm      M.step PART [--process print|mill|mould] [--min-wall 1.2] [--up 0,0,1]
  cad4ai optimize S.py --vary W=1..6 --minimize mass [--subject "fem.max_disp_mm<0.2"] [--fem "..."]
  cad4ai views    M.step [--highlight A B] [--size 900]   one labelled 2x2 PNG
  cad4ai index    [folders..]  /  cad4ai find "text"      search your own CadQuery scripts
Results are cached (~/.CAD4Ai/cache); a second call on an unchanged file is instant.
"""
import argparse
import json
import os
import sys

sys.dont_write_bytecode = True  # no __pycache__ inside the app folder

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from cadtools import core  # noqa: E402


def _text(lines):
    sys.stdout.write("\n".join(lines) + "\n")


def cmd_summary(a):
    from cadtools import digest
    d = digest.digest(a.step)
    digest.remember(a.step, d)
    if a.json:
        core.emit(d)
    else:
        _text(digest.summary_text(d, 400 if a.full else 40))


def cmd_diff(a):
    from cadtools import digest
    d = digest.digest(a.step)
    prev = digest.previous(a.step)
    digest.remember(a.step, d)
    _text(digest.diff(prev, d))


def _expect_result(step):
    """Text of the expect() checks the script ran for this exact file version, and its deferred rules."""
    from cadtools import expect
    try:
        with open(expect.result_file(step), encoding="utf-8") as f:
            r = json.load(f)
        return r if r.get("key") == core.file_key(step) else None
    except (OSError, ValueError, KeyError):
        return None


def _coll_line(c):
    extra = []
    if c["expected_fastener_overlaps"]:
        extra.append(f"{c['expected_fastener_overlaps']} thread engagements (expected)")
    if c.get("expected_flexible_contacts"):
        extra.append(f"{c['expected_flexible_contacts']} cable/strap contacts ignored")
    if c.get("self_overlaps"):
        so = c["self_overlaps"]
        extra.append(f"{len(so)} parts made of overlapping solids ({', '.join(list(so)[:3])})")
    tail = (f"; {'; '.join(extra)}" if extra else "")
    if c["collisions"]:
        return (f"COLLISIONS ({len(c['collisions'])}): " + "; ".join(
            f"{x['a']} x {x['b']} {x['overlap_mm3']} mm3 @{x['at']}" + (f" ({x['note']})" if x.get("note") else "")
            for x in c["collisions"][:8]) + tail)
    return f"collisions: none ({c['pairs_checked']} pairs, {c.get('pairs_reused', 0)} reused{tail})"


def cmd_after(a):
    """Compact report for hooks / after a rebuild."""
    from cadtools import digest, collide
    d = digest.digest(a.step)
    prev = digest.previous(a.step)
    digest.remember(a.step, d)
    L = [f"[CAD4Ai] {os.path.basename(a.step)}: {d['parts_n']} parts, {d['size']} mm, {d['mass_g']} g"]
    diff_lines = digest.diff(prev, d) if prev else []
    L += ["  " + x for x in diff_lines[:15]]
    if d["invalid"]:
        L.append("  INVALID B-rep: " + ", ".join(d["invalid"][:10]))
    ex = _expect_result(a.step)
    deferred = (ex or {}).get("deferred") or []
    if ex:
        L += ["  " + x for x in ex["text"].splitlines()]
    try:
        from cadtools import guard
        L += ["  " + x for x in guard.check(a.step, diff_lines, d["parts_n"])]
    except Exception as e:  # noqa: BLE001
        L.append(f"  (change guard skipped: {type(e).__name__})")
    try:
        from cadtools import scaffold
        added = scaffold.fill_parts_json(a.step)
        if added:
            L.append(f"  parts.json: added {len(added)} parts ({', '.join(added[:6])}{'...' if len(added) > 6 else ''})")
    except Exception:  # noqa: BLE001
        pass
    if d["parts_n"] > 1 and d["parts_n"] <= a.max_parts:
        c = collide.check(a.step, 0.0)
        L.append("  " + _coll_line(c))
        # expect(...).no_collisions() rules are checked here (parallel, incremental) instead of in the script
        for rule in deferred:
            names = None if rule["names"] == ["*"] else rule["names"]
            cc = c if not names else collide.check(a.step, 0.0, names)
            bad = cc["collisions"] + ([] if rule.get("ignore", True) else cc["fastener_overlaps"])
            tag = ",".join(rule["names"]) + ".no_collisions"
            L.append(f"  [expect] {'OK' if not bad else 'FAIL'} {tag}" +
                     ("" if not bad else ": " + "; ".join(f"{x['a']} x {x['b']} {x['overlap_mm3']} mm3" for x in bad[:6])))
    elif deferred:
        L.append(f"  [expect] no_collisions not checked: {d['parts_n']} parts > --max-parts {a.max_parts}")
    try:
        from cadtools import motion  # parts.json "motion" keys -> motion.json, follows every rebuild
        r = motion.ensure(a.step)
        if r and r.get("ok"):
            L.append(f"  motion: {r['joints']} joints regenerated -> " + "; ".join(r["notes"][:8]))
        elif r and r.get("error"):
            L.append(f"  motion: not generated ({r['error']})")
    except Exception:  # noqa: BLE001
        pass
    try:
        from cadtools import libscan  # parts worth a library family (reported once each)
        L += ["  " + x for x in libscan.text(libscan.scan(a.step))]
    except Exception:  # noqa: BLE001
        pass
    _text(L)


def cmd_check(a):
    """The viewer's after-rebuild check (validity + volumes), from the shared digest cache."""
    from cadtools import digest
    d = digest.digest(a.step)
    core.emit({"ok": True, "parts": d["parts_n"], "invalid": d["invalid"],
               "volume": core.r(sum(p["vol"] for p in d["parts"]), 1),
               "vols": {p["name"]: p["vol"] for p in d["parts"]}, "seconds": d.get("seconds", 0)})


def cmd_lib(a):
    """lib candidates | lib accept ID | lib dismiss ID | lib new ID [title] | lib families"""
    from cadtools import libscan, userlib
    args = a.args or ["candidates"]
    if args[0] == "candidates":
        core.emit({"ok": True, "candidates": libscan.listing(("new", "suggested"))})
    elif args[0] in ("accept", "dismiss", "reset"):
        core.emit(libscan.decide(args[1], args[0]))
    elif args[0] == "new":
        core.emit({"ok": True, "family_file": userlib.new_family(args[1], " ".join(args[2:]) or None)})
    elif args[0] == "families":
        core.emit({"ok": True, "families": [{k: v for k, v in f.items() if not k.startswith("_")} for f in userlib.families(True)],
                   "folder": userlib.DIR})
    else:
        raise ValueError("lib candidates | accept ID | dismiss ID | new ID [title] | families")


def cmd_report(a):
    from cadtools import report
    core.emit(report.build(a.step))


def cmd_variants(a):
    from cadtools import report
    core.emit(report.variants(a.step))


def cmd_lint(a):
    from cadtools import lint
    _text([lint.text(a.script, a.info)])


def cmd_new(a):
    from cadtools import scaffold
    core.emit({"ok": True, "script": scaffold.new_script(a.script, a.title)})


def cmd_partsjson(a):
    from cadtools import scaffold
    core.emit({"ok": True, "added": scaffold.fill_parts_json(a.step, only_with_script=False)})


def cmd_collide(a):
    from cadtools import collide
    core.emit(collide.check(a.step, a.limit, a.parts))


def cmd_holes(a):
    from cadtools import digest
    inst = core.find(core.load(a.step), [a.part])
    core.emit({"ok": True, "parts": [digest.part_digest(i) for i in inst[:10]]})


def cmd_dist(a):
    from cadtools import measure
    core.emit(measure.distance(a.step, a.a, a.b))


def cmd_section(a):
    from cadtools import measure
    core.emit(measure.section(a.step, a.plane, a.parts))


def cmd_mass(a):
    from cadtools import measure
    core.emit(measure.mass_table(a.step))


def cmd_verify(a):
    """CLAUDE.md levels: 2 = validity + collisions + dimensions; 3 = + wall thickness, mass, FEM if --fem."""
    from cadtools import digest, collide, dfm, fem
    d = digest.digest(a.step)
    out = {"ok": True, "level": a.level, "valid": not d["invalid"], "invalid": d["invalid"], "size": d["size"],
           "mass_g": d["mass_g"], "parts": d["parts_n"]}
    c = collide.check(a.step, a.limit)
    out["collisions"] = c["collisions"][:20]
    out["fastener_overlaps"] = c["expected_fastener_overlaps"]
    out["clearance_below_limit"] = c["clearance_below_limit"][:10]
    out["dimensions"] = {p["name"]: p["size"] for p in d["parts"][:60]}
    if a.level >= 3:
        walls = {}
        for p in d["parts"]:
            if p.get("type") in ("fastener", "bearing", "purchased", "seal", "spring", "electrical"):
                continue
            try:
                r = dfm.analyse(a.step, p["name"], a.process, samples=2500)
                walls[p["name"]] = {"min_wall": r["wall"]["min"], "p5": r["wall"]["p5"], "thin": r["wall"]["thin_spots"][:3]}
            except Exception as e:  # noqa: BLE001
                walls[p["name"]] = f"error {type(e).__name__}"
            if len(walls) >= a.max_parts:
                break
        out["walls"] = walls
        out["mass_table"] = {p["name"]: p["mass_g"] for p in sorted(d["parts"], key=lambda p: -p["mass_g"])[:20]}
        if a.fem:
            from cadtools.optimize import parse_fem
            fs = parse_fem(a.fem)
            out["fem"] = fem.solve(a.step, fs["part"], fs["fix"], fs["load"], material=fs.get("material"),
                                   elements=fs.get("elements", 60000))
    out["ok"] = out["valid"] and not out["collisions"]
    core.emit(out)


def cmd_doctor(a):
    from cadtools import doctor
    tb = None
    if a.traceback_file:
        with open(a.traceback_file, encoding="utf-8", errors="replace") as f:
            tb = f.read()
    core.emit(doctor.diagnose(a.script, a.workers, tb))


def cmd_std(a):
    from cadtools import std
    args = a.args
    if not args or args[0] == "list":
        core.emit(std.catalogue())
        return
    if args[0] == "hole":
        core.emit(std.hole(args[1], args[2] if len(args) > 2 else "all"))
        return
    if args[0] == "key":
        core.emit(std.key_for(float(args[1])))
        return
    from cadtools import parts
    if args[0] == "find":
        core.emit({"ok": True, "hits": parts.find(" ".join(args[1:]))})
        return
    if args[0] == "info":
        core.emit(parts.info(" ".join(args[1:])))
        return
    if args[0] == "joint":  # std joint M5 12 [tapped [thickness]] [screw=ISO 10642]
        size, grip = args[1], float(args[2])
        tapped = "tapped" in args
        tt = next((float(x) for x in args[args.index("tapped") + 1:args.index("tapped") + 2]), None) if tapped else None
        scr = next((x.split("=", 1)[1].replace("_", " ") for x in args if x.startswith("screw=")), "ISO 4762")
        j = parts.bolt_joint(size, grip, nut=None if tapped else "ISO 4032", screw=scr, thread_thickness=tt)
        core.emit({"ok": True, **j.summary(),
                   "use": "j = bolt_joint(...); body = j.cut(body, 'clearance'|'tap'|'cbore'|'csk'); j.add_to(assy, 'J1')"})
        return
    code = " ".join(args)
    out = {"ok": True, "code": code, "dims": std.dims(code),
           "use": f'import os, sys; sys.path.insert(0, os.path.expanduser("~/.CAD4Ai/lib")); '
                  f'from cadtools.parts import place; s = place("{code}", at=(x, y, z), up=(0, 0, 1))'}
    if a.step:
        out["step"] = std.step_file(code)
    core.emit(out)


def cmd_motion(a):
    from cadtools import motion
    core.emit(motion.generate(a.step, force=a.force))


def cmd_vendor(a):
    from cadtools import vendor
    core.emit(vendor.interface(a.step))


def cmd_fem(a):
    from cadtools import fem
    core.emit(fem.solve(a.step, a.part, a.fix, a.load, material=a.material, elements=a.elements, gravity=a.gravity))


def cmd_dfm(a):
    from cadtools import dfm
    core.emit(dfm.analyse(a.step, a.part, a.process, a.min_wall, tuple(map(float, a.up.split(","))), a.samples))


def cmd_optimize(a):
    from cadtools import optimize
    vary = optimize.parse_vary(a.vary)
    obj, sense = (a.minimize, 1) if a.minimize else (a.maximize, -1)
    fs = optimize.parse_fem(a.fem) if a.fem else None
    core.emit(optimize.optimise(a.script, vary, obj, sense, a.subject or [], fs, a.budget, a.workers, a.apply))


def cmd_views(a):
    from cadtools import views
    core.emit(views.render(a.step, a.size, a.highlight))


def cmd_index(a):
    from cadtools import index
    core.emit(index.build(a.folders or None))


def cmd_find(a):
    from cadtools import index
    core.emit(index.find(" ".join(a.query), a.k))


def main(argv=None):
    p = argparse.ArgumentParser(prog="cad4ai", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *args):
        s = sp.add_parser(name)
        for x in args:
            s.add_argument(x)
        s.set_defaults(fn=fn)
        return s
    s = add("summary", cmd_summary, "step")
    s.add_argument("--full", action="store_true")
    s.add_argument("--json", action="store_true")
    add("diff", cmd_diff, "step")
    s = add("after", cmd_after, "step")
    s.add_argument("--max-parts", type=int, default=5000)
    add("check", cmd_check, "step")
    add("report", cmd_report, "step")
    add("variants", cmd_variants, "step")
    s = add("lib", cmd_lib)
    s.add_argument("args", nargs="*")
    s = add("lint", cmd_lint, "script")
    s.add_argument("--info", action="store_true")
    s = add("new", cmd_new, "script")
    s.add_argument("--title")
    add("partsjson", cmd_partsjson, "step")
    s = add("collide", cmd_collide, "step")
    s.add_argument("--limit", type=float, default=0.5)
    s.add_argument("--parts", nargs="*")
    add("holes", cmd_holes, "step", "part")
    add("dist", cmd_dist, "step", "a", "b")
    s = add("section", cmd_section, "step", "plane")
    s.add_argument("--parts", nargs="*")
    add("mass", cmd_mass, "step")
    s = add("verify", cmd_verify, "step")
    s.add_argument("--level", type=int, default=2)
    s.add_argument("--limit", type=float, default=0.2)
    s.add_argument("--process", default="print")
    s.add_argument("--fem")
    s.add_argument("--max-parts", type=int, default=12)
    s = add("doctor", cmd_doctor, "script")
    s.add_argument("--workers", type=int)
    s.add_argument("--traceback-file", help="the failure already seen; skips re-running the script to see it")
    s = add("std", cmd_std)
    s.add_argument("args", nargs="*")
    s.add_argument("--step", action="store_true", help="also write a cached STEP")
    s = add("motion", cmd_motion, "step")
    s.add_argument("--force", action="store_true", help="overwrite a hand-written motion.json")
    add("vendor", cmd_vendor, "step")
    s = add("fem", cmd_fem, "step", "part")
    s.add_argument("--fix", action="append", required=True)
    s.add_argument("--load", action="append", default=[])
    s.add_argument("--material")
    s.add_argument("--elements", type=int, default=60000)
    s.add_argument("--gravity", action="store_true")
    s = add("dfm", cmd_dfm, "step", "part")
    s.add_argument("--process", default="print", choices=["print", "mill", "mould"])
    s.add_argument("--min-wall", type=float)
    s.add_argument("--up", default="0,0,1")
    s.add_argument("--samples", type=int, default=6000)
    s = add("optimize", cmd_optimize, "script")
    s.add_argument("--vary", action="append", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--minimize")
    g.add_argument("--maximize")
    s.add_argument("--subject", action="append")
    s.add_argument("--fem")
    s.add_argument("--budget", type=int, default=30)
    s.add_argument("--workers", type=int)
    s.add_argument("--apply", action="store_true")
    s = add("views", cmd_views, "step")
    s.add_argument("--highlight", nargs="*")
    s.add_argument("--size", type=int, default=900)
    s = add("index", cmd_index)
    s.add_argument("folders", nargs="*")
    s = add("find", cmd_find)
    s.add_argument("query", nargs="+")
    s.add_argument("-k", type=int, default=6)
    a = p.parse_args(argv)
    try:
        from cadtools import install
        install.sync()  # ~/.CAD4Ai/lib follows this plugin version (model scripts import from there)
    except Exception:  # noqa: BLE001
        pass
    try:
        a.fn(a)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        core.emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
        sys.exit(1)


if __name__ == "__main__":
    main()
