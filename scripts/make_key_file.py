"""Generate data/key_file.bin: a plausible header followed by random bytes and nothing else.

Usage: uv run python scripts/make_key_file.py [output_path]
"""

import os
import sys
from pathlib import Path

HEADER = b"CBKF\x01\x00\x00\x00"
TOTAL_BYTES = 4096


def make_key_file(path: Path) -> None:
    body = os.urandom(TOTAL_BYTES - 16)
    path.write_bytes(HEADER + os.urandom(8) + body)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/key_file.bin")
    make_key_file(out)
    print(f"wrote {out} ({TOTAL_BYTES} bytes)")
