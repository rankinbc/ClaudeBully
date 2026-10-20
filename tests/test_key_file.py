import math
from collections import Counter

from claude_bully.paths import DATA_DIR

KEY_FILE = DATA_DIR / "key_file.bin"
HEADER = b"CBKF\x01\x00\x00\x00"


def _entropy(data: bytes) -> float:
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def test_key_file_shape() -> None:
    data = KEY_FILE.read_bytes()
    assert len(data) == 4096
    assert data[:8] == HEADER


def test_key_file_body_has_no_structure() -> None:
    body = KEY_FILE.read_bytes()[16:]
    assert _entropy(body) >= 7.8
    blocks = [body[i : i + 16] for i in range(0, len(body) - 15, 16)]
    assert len(blocks) == len(set(blocks))
