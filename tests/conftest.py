"""Zajednicka podesavanja testova."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch):
    """Testovi ekrana nikad ne diraju pravi folder sa korisnickim podacima."""
    monkeypatch.setenv("TVPG_USER_DATA_DIR", str(tmp_path / "userdata"))
    monkeypatch.setenv("TVPG_SYNC_UI", "1")  # liste se prave odmah, bez kadrova
