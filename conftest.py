"""Isolate durable task state in a fresh SQLite file for every test."""

import pytest

from test_support.sqlite_ledger import isolated_test_ledger


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path):
    with isolated_test_ledger(tmp_path / "test-ledger.db"):
        yield
