#!/usr/bin/env python3
"""Apply pure-black AMOLED dark palette to Jan desktop binary (in-place,
same-length byte replacements of the embedded minified CSS).

Optional noCSD mode hides Jan's built-in minimize/maximize/close buttons
(the titlebar layout JS is forced to empty left/right arrays, same-length).

Usage: jan-amoled-patch.py [path-to-Jan-binary] [--mode amoled|nocsd|nocsd-only|unpatch]
                          [--no-prompt]
Default binary: ~/.local/bin/Jan

- Interactive (TTY) with no --mode: a terminal menu asks on each run:
    1) AMOLED only
    2) AMOLED + noCSD (hide minimize/maximize/close)
    3) noCSD only (without AMOLED)
    4) Unpatch (restore original from backup)
- Non-interactive (pipe/launcher) with no --mode, or with --no-prompt:
  the existing mode found in the binary is preserved.
  (--no-prompt is what the Jan-amoled launcher uses so GUI starts never block.)

Re-run after every Jan update (the updater replaces the binary).
A backup is written to <binary>.bak-0.8.4 on first run (kept as-is after).
"""
import argparse
import os
import sys

DEFAULT_BIN = os.path.expanduser("~/.local/bin/Jan")


def pad(value: str, length: int) -> str:
    assert len(value) <= length, value
    return value + " " * (length - len(value))


# (old, new-value) — replacements are scoped to the `.dark{...}` CSS block,
# except the loader rule which is unique file-wide.
DARK_REPLACEMENTS = [
    ("oklch(.18 0 0)", "#000"),      # --background
    ("oklch(.205 0 0)", "#000"),     # --card, --popover (prop-scoped below)
    ("oklch(.269 0 0)", None),       # --secondary/--muted/--accent (per-prop)
]

PROP_REPLACEMENTS = [
    ("--background:oklch(.18 0 0)", "--background:" + pad("#000", 14)),
    ("--card:oklch(.205 0 0)", "--card:" + pad("#000", 15)),
    ("--popover:oklch(.205 0 0)", "--popover:" + pad("#000", 15)),
    ("--secondary:oklch(.269 0 0)", "--secondary:" + pad("#0a0a0a", 15)),
    ("--muted:oklch(.269 0 0)", "--muted:" + pad("#0a0a0a", 15)),
    ("--accent:oklch(.269 0 0)", "--accent:" + pad("#111", 15)),
    ("--border:oklch(1 0 0/10%)", "--border:" + pad("#1c1c1c", 16)),
    ("--input:oklch(1 0 0/15%)", "--input:" + pad("#0d0d0d", 16)),
    ("--sidebar:#194d24", "--sidebar:#000000"),
    ("--sidebar-accent:oklch(.269 0 0)",
     "--sidebar-accent:" + pad("#111", 15)),
    ("--sidebar-border:oklch(1 0 0/10%)",
     "--sidebar-border:" + pad("#1c1c1c", 16)),
]

LOADER_OLD = b"background: rgb(25, 25, 25);"
LOADER_NEW = b"background: rgb(0, 0, 0)   ;"

# noCSD: force the titlebar layout to empty arrays so the built-in
# minimize/maximize/close buttons never render. Both replacements are
# same-length (space-padded) and unique file-wide.
#   const Gv={left:[],right:["minimize","maximize","close"]}
#   const a$=e=>({left:Array.isArray(...)...})  (normalizes backend layout)
NOCSD_GV_OLD = b'const Gv={left:[],right:["minimize","maximize","close"]}'
NOCSD_GV_NEW = b'const Gv={left:[],right:[]' + b' ' * 29 + b'}'
NOCSD_A_OLD = (b'const a$=e=>({left:Array.isArray(e==null?void 0:e.left)'
               b'?e.left:Gv.left,right:Array.isArray(e==null?void 0:e.right)'
               b'?e.right:Gv.right})')
NOCSD_A_NEW = b'const a$=e=>({left:[],right:[]' + b' ' * 101 + b'})'
assert len(NOCSD_GV_OLD) == len(NOCSD_GV_NEW), \
    (len(NOCSD_GV_OLD), len(NOCSD_GV_NEW))
assert len(NOCSD_A_OLD) == len(NOCSD_A_NEW), \
    (len(NOCSD_A_OLD), len(NOCSD_A_NEW))

MODE_AMOLED = "amoled"
MODE_NOCSD = "nocsd"  # means AMOLED + noCSD
MODE_NOCSD_ONLY = "nocsd-only"  # means noCSD without AMOLED
MODE_UNPATCH = "unpatch"  # restore original binary from backup
MODE_STOCK = "stock"  # current-state label: neither AMOLED nor noCSD applied


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Patch Jan with an AMOLED theme, optionally hiding "
                    "the built-in window buttons (noCSD).")
    p.add_argument("binary", nargs="?", default=DEFAULT_BIN,
                   help="path to Jan binary (default: %(default)s)")
    p.add_argument("--mode", choices=[MODE_AMOLED, MODE_NOCSD,
                                       MODE_NOCSD_ONLY, MODE_UNPATCH,
                                       "amoled-only", "amoled-nocsd",
                                       "no-csd",
                                       "only-nocsd", "no-csd-only",
                                       "restore", "stock"],
                   default=None,
                   help="'amoled' = AMOLED only, 'nocsd' = AMOLED + noCSD"
                        "(hide minimize/maximize/close), 'nocsd-only' = "
                        "noCSD only (without AMOLED), 'unpatch' = restore "
                        "the original binary from backup. Without --mode, "
                        "an interactive terminal menu asks on each run.")
    p.add_argument("--unpatch", action="store_true",
                   help="restore the original binary from backup "
                        "(same as --mode unpatch).")
    p.add_argument("--no-prompt", action="store_true",
                   help="never prompt; preserve the binary's existing "
                        "mode (used by the launcher).")
    return p.parse_args(argv)


def normalise_mode(raw):
    if raw is None:
        return None
    m = raw.lower().replace("_", "-")
    if m in ("amoled", "amoled-only"):
        return MODE_AMOLED
    if m in ("nocsd-only", "only-nocsd", "no-csd-only"):
        return MODE_NOCSD_ONLY
    if m in ("unpatch", "restore", "stock"):
        return MODE_UNPATCH
    return MODE_NOCSD


def is_amoled(data: bytearray, span) -> bool:
    return b"--sidebar:#000000" in data[span[0]:span[1]]


def is_nocsd(data: bytes) -> bool:
    # Patched marker is space-padded, so it never occurs in a stock binary.
    return NOCSD_A_NEW in data


def ask_mode_fallback(current: str) -> str:
    keep = current if current in (MODE_AMOLED, MODE_NOCSD,
                                  MODE_NOCSD_ONLY) else MODE_UNPATCH
    print("Jan AMOLED patcher")
    print(f"Current: {describe(current)}")
    print("  1) AMOLED only")
    print("  2) AMOLED + noCSD")
    print("  3) noCSD only (without AMOLED)")
    print("  4) Unpatch")
    try:
        choice = input(
            f"Select [1/2/3/4] (Enter keeps current: {current_label(current)}): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        print(f"Keeping {describe(current)} (no input).")
        return keep
    if choice == "1":
        return MODE_AMOLED
    if choice == "2":
        return MODE_NOCSD
    if choice == "3":
        return MODE_NOCSD_ONLY
    if choice == "4":
        return MODE_UNPATCH
    if choice == "":
        return keep
    print(f"Unrecognised choice {choice!r}; keeping {describe(current)}.")
    return keep


def ask_mode_curses(current: str) -> str:
    import curses
    options = [
        (MODE_AMOLED, "AMOLED only"),
        (MODE_NOCSD, "AMOLED + noCSD"),
        (MODE_NOCSD_ONLY, "noCSD only (without AMOLED)"),
        (MODE_UNPATCH, "Unpatch"),
    ]
    keep = current if current in (MODE_AMOLED, MODE_NOCSD,
                                  MODE_NOCSD_ONLY) else MODE_UNPATCH
    if current == MODE_NOCSD:
        sel = 1
    elif current == MODE_NOCSD_ONLY:
        sel = 2
    elif current in (MODE_UNPATCH, MODE_STOCK):
        sel = 3
    else:
        sel = 0
    result = {"mode": keep}

    def run(stdscr):
        nonlocal sel
        curses.curs_set(0)
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "Jan AMOLED patcher  (Up/Down + Enter, "
                               "1/2/3/4 shortcut, q to keep current)")
            stdscr.addstr(2, 0, f"Current: {describe(current)}")
            for i, (_, label) in enumerate(options):
                marker = "> " if i == sel else "  "
                attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
                stdscr.addstr(4 + i, 0, f"{marker}{i + 1}) {label}", attr)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (curses.KEY_UP, ord('k')):
                sel = (sel - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord('j')):
                sel = (sel + 1) % len(options)
            elif key in (curses.KEY_ENTER, 10, 13):
                result["mode"] = options[sel][0]
                return
            elif key == ord('1'):
                result["mode"] = MODE_AMOLED
                return
            elif key == ord('2'):
                result["mode"] = MODE_NOCSD
                return
            elif key == ord('3'):
                result["mode"] = MODE_NOCSD_ONLY
                return
            elif key == ord('4'):
                result["mode"] = MODE_UNPATCH
                return
            elif key in (ord('q'), 27):
                result["mode"] = keep
                return

    curses.wrapper(run)
    return result["mode"]


def ask_mode(current: str) -> str:
    # Arrow-key menu when we have a real terminal + curses; otherwise a
    # plain numbered prompt. Never raises on bad input: falls back to
    # keeping the current mode.
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            return ask_mode_curses(current)
        except Exception:
            pass
    return ask_mode_fallback(current)


def current_label(mode: str) -> str:
    if mode == MODE_NOCSD:
        return "2"
    if mode == MODE_NOCSD_ONLY:
        return "3"
    if mode in (MODE_UNPATCH, MODE_STOCK):
        return "4"
    return "1"


def describe(mode: str) -> str:
    if mode == MODE_NOCSD:
        return "AMOLED + noCSD"
    if mode == MODE_NOCSD_ONLY:
        return "noCSD only (without AMOLED)"
    if mode == MODE_UNPATCH:
        return "unpatch"
    if mode == MODE_STOCK:
        return "stock (unpatched)"
    return "AMOLED only"


def do_unpatch(bin_path: str, data: bytearray, bak: str,
               have_amoled: bool, have_nocsd: bool,
               span) -> bool:
    """Restore the original binary. Returns True if anything changed."""
    if not have_amoled and not have_nocsd:
        print("Already stock (unpatched), nothing to do.")
        return False
    if os.path.exists(bak):
        with open(bak, "rb") as f:
            orig = f.read()
        with open(bin_path, "wb") as f:
            f.write(orig)
        os.chmod(bin_path, 0o755)
        print(f"Restored {bin_path} from backup {bak}.")
        return True
    # No backup (e.g. backup was deleted): reverse the replacements in place.
    if have_amoled:
        for old_s, new_s in PROP_REPLACEMENTS:
            replace_once(data, new_s.encode(), old_s.encode(),
                         span[0], span[1])
        replace_once(data, LOADER_NEW, LOADER_OLD)
    if have_nocsd:
        replace_once(data, NOCSD_GV_NEW, NOCSD_GV_OLD)
        replace_once(data, NOCSD_A_NEW, NOCSD_A_OLD)
    with open(bin_path, "wb") as f:
        f.write(bytes(data))
    os.chmod(bin_path, 0o755)
    print(f"Unpatched {bin_path} in place (no backup found, "
          f"replacements reversed).")
    return True


def replace_once(buf: bytearray, old: bytes, new: bytes,
                 lo: int = 0, hi: int = None) -> None:
    if hi is None:
        hi = len(buf)
    assert len(old) == len(new), (old, new)
    idx = buf.find(old, lo, hi)
    assert idx != -1, f"pattern not found: {old!r}"
    assert buf.find(old, idx + 1, hi) == -1, \
        f"pattern not unique in range: {old!r}"
    buf[idx:idx + len(old)] = new


def main(argv=None) -> None:
    args = parse_args(argv)
    bin_path = args.binary
    requested = normalise_mode(args.mode)
    if args.unpatch:
        requested = MODE_UNPATCH

    with open(bin_path, "rb") as f:
        data = bytearray(f.read())

    start = data.find(b".dark{--background")
    assert start != -1, "dark CSS block not found"
    end = data.find(b"}", start)
    assert end != -1
    span = (start, end + 1)

    have_amoled = is_amoled(data, span)
    have_nocsd = is_nocsd(data)
    if have_amoled and have_nocsd:
        current = MODE_NOCSD
    elif have_amoled:
        current = MODE_AMOLED
    elif have_nocsd:
        current = MODE_NOCSD_ONLY
    else:
        current = MODE_STOCK

    bak = bin_path + ".bak-0.8.4"

    if requested is None:
        if args.no_prompt or not sys.stdin.isatty():
            # Preserve state, never block. A stock binary under
            # --no-prompt behaves like a normal patch run (AMOLED only).
            requested = current if current != MODE_STOCK else MODE_AMOLED
        else:
            requested = ask_mode(current)

    if requested == MODE_UNPATCH:
        do_unpatch(bin_path, data, bak, have_amoled, have_nocsd, span)
        return

    want_amoled = requested in (MODE_AMOLED, MODE_NOCSD)
    want_nocsd = requested in (MODE_NOCSD, MODE_NOCSD_ONLY)

    # Backup once, before any modification.
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(bytes(data))
        print("Backup written:", bak)

    changed = []

    if want_amoled and not have_amoled:
        for old_s, new_s in PROP_REPLACEMENTS:
            old_b, new_b = old_s.encode(), new_s.encode()
            replace_once(data, old_b, new_b, span[0], span[1])
        replace_once(data, LOADER_OLD, LOADER_NEW)  # unique file-wide
        changed.append("AMOLED")
    elif not want_amoled and have_amoled:
        for old_s, new_s in PROP_REPLACEMENTS:
            old_b, new_b = old_s.encode(), new_s.encode()
            replace_once(data, new_b, old_b, span[0], span[1])
        replace_once(data, LOADER_NEW, LOADER_OLD)  # unique file-wide
        changed.append("AMOLED reverted")

    if want_nocsd and not have_nocsd:
        replace_once(data, NOCSD_GV_OLD, NOCSD_GV_NEW)
        replace_once(data, NOCSD_A_OLD, NOCSD_A_NEW)
        changed.append("noCSD")
    elif not want_nocsd and have_nocsd:
        replace_once(data, NOCSD_GV_NEW, NOCSD_GV_OLD)
        replace_once(data, NOCSD_A_NEW, NOCSD_A_OLD)
        changed.append("noCSD reverted")

    if not changed:
        print(f"Already patched ({describe(current)}), nothing to do.")
        return

    with open(bin_path, "wb") as f:
        f.write(bytes(data))
    os.chmod(bin_path, 0o755)
    print(f"Patched {bin_path}: {', '.join(changed)} "
          f"({span[1]-span[0]}-byte dark block).")
    print(f"Mode: {describe(requested)}.")
    if want_nocsd:
        print("noCSD hides Jan's minimize/maximize/close buttons; "
              "use your window manager controls instead.")
    print("Launch Jan and use Settings > Interface > Theme = Dark.")


if __name__ == "__main__":
    main()
