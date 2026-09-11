import pytest

pytestmark = pytest.mark.integration


def test_marker_canary():
    """Permanent guard for the marker + RELAY_ITEST gate mechanics.
    Starts no session, so it is money-free even under `make itest`."""
    assert True
