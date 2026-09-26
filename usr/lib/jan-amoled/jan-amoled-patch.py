#!/usr/bin/env python3
"""Apply pure-black AMOLED dark palette to Jan desktop binary (in-place,
same-length byte replacements of the embedded minified CSS).

Usage: jan-amoled-patch.py [path-to-Jan-binary]
Default: ~/.local/bin/Jan

Re-run after every Jan update (the updater replaces the binary).
A backup is written to <binary>.bak-0.8.4 on first run (kept as-is after).
"""
import sys
import os

BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.local/bin/Jan")


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


def main() -> None:
    with open(BIN, "rb") as f:
        data = bytearray(f.read())

    start = data.find(b".dark{--background")
    assert start != -1, "dark CSS block not found"
    end = data.find(b"}", start)
    assert end != -1
    span = (start, end + 1)

    # Already patched? (idempotent)
    if b"--sidebar:#000000" in data[span[0]:span[1]]:
        print("Already AMOLED-patched, nothing to do.")
        return

    # Backup once
    bak = BIN + ".bak-0.8.4"
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(bytes(data))
        print("Backup written:", bak)

    def replace_once(buf: bytes, old: bytes, new: bytes,
                     lo: int = 0, hi: int = len(data)) -> None:
        assert len(old) == len(new), (old, new)
        idx = buf.find(old, lo, hi)
        assert idx != -1, f"pattern not found: {old!r}"
        assert buf.find(old, idx + 1, hi) == -1, \
            f"pattern not unique in range: {old!r}"
        buf[idx:idx + len(old)] = new

    for old_s, new_s in PROP_REPLACEMENTS:
        old_b, new_b = old_s.encode(), new_s.encode()
        replace_once(data, old_b, new_b, span[0], span[1])

    replace_once(data, LOADER_OLD, LOADER_NEW)  # unique file-wide

    with open(BIN, "wb") as f:
        f.write(bytes(data))
    os.chmod(BIN, 0o755)
    print(f"Patched {BIN} ({span[1]-span[0]}-byte dark block + loader).")
    print("Launch Jan and use Settings > Interface > Theme = Dark.")


if __name__ == "__main__":
    main()
