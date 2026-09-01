from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
GOLDEN = ROOT / "golden"


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def golden() -> Path:
    return GOLDEN
