"""Fixed prompt files: the target's baseline system prompt, the defender, the bully framing."""

from functools import cache

from claude_bully.paths import DATA_DIR

TARGET_SYSTEM_PATH = DATA_DIR / "target_system.md"
DEFENDER_PATH = DATA_DIR / "defender.md"
BULLY_FRAMING_PATH = DATA_DIR / "bully_framing.md"


@cache
def _read(path_name: str) -> str:
    return (DATA_DIR / path_name).read_text(encoding="utf-8").strip()


def load_target_system(display_name: str, defender: bool) -> str:
    base = _read(TARGET_SYSTEM_PATH.name).replace("{display_name}", display_name)
    if defender:
        return f"{base}\n\n{_read(DEFENDER_PATH.name)}"
    return base


def load_bully_framing() -> str:
    return _read(BULLY_FRAMING_PATH.name)
