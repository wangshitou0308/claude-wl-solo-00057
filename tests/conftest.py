"""pytest 共享夹具。"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.engine.decision import RepairDecisionEngine

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalogs"


@pytest.fixture(scope="session")
def app():
    return create_app(CATALOG_DIR)


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture(scope="session")
def engine(app) -> RepairDecisionEngine:
    return app.state.engine


BASE_PAYLOAD = {
    "device_model": "TERM-A7",
    "hardware_revision": "REV-2",
    "installed_part": "SSD-128",
    "fault_code": "F001",
    "catalog_version": "2025.1",
    "measurements": {
        "smart_log": "complete",
        "firmware_version": "2.0.0",
    },
}
