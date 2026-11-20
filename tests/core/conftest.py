import pytest

from tests.core.helpers import fresh_project


@pytest.fixture
def project():
    """(state, cache): the shared layout, every node fresh, every result in the cache."""
    return fresh_project()
