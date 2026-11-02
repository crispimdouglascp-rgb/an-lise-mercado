import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Projeto isolado em pasta temporária, com a config real e dados vazios."""
    shutil.copytree(RAIZ / "config", tmp_path / "config")
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "data" / "diario").mkdir()
    monkeypatch.setenv("RVLOCAL_HOME", str(tmp_path))
    monkeypatch.delenv("RVLOCAL_AGORA", raising=False)
    return tmp_path
