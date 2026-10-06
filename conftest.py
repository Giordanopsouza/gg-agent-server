"""Clean rows created by local Postgres ledger tests after each case."""

import pytest

from test_support.postgres_ledger import clean_test_ledger


@pytest.fixture(autouse=True)
def _clean_local_ledger():
    yield
    clean_test_ledger()
