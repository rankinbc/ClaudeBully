from claude_bully import __version__
from claude_bully.paths import CONFIGS_DIR, DATA_DIR


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_data_dir_exists() -> None:
    assert DATA_DIR.is_dir() and DATA_DIR.name == "data"
    assert CONFIGS_DIR.name == "configs"
