# Everything under seeds/ is a sandbox fixture, not a test the relay suite runs.
# The toy project ships its own test_*.py so the sandbox /verify has something to
# run; without this guard a bare `pytest tests/` (CI's invocation) would collect
# those fixture tests and error on the tests/integration RELAY_ITEST gate. The
# toy project still runs standalone from its own rootdir, where this conftest is
# above the confcutdir and never loads.
collect_ignore_glob = ["*"]
