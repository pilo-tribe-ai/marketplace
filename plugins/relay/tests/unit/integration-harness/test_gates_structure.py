# plugins/relay/tests/unit/integration-harness/test_gates_structure.py

EXPECTED = [
    "test_verify_refuses_main",
    "test_verify_refuses_detached_head",
    "test_unsupported_engine",
    "test_rounds_out_of_range",
    "test_floor_gate",
    "test_preflight_provenance",
]


def test_all_six_gate_cases_are_collected(collect_integration):
    # -m integration wins over pytest.ini's addopts, so a missing marker on the
    # tier file would deselect every case and drop these names — this is also the
    # marker guard.
    out = collect_integration("tests/integration/test_gates.py").stdout
    for name in EXPECTED:
        assert name in out, f"{name} not collected:\n{out}"
