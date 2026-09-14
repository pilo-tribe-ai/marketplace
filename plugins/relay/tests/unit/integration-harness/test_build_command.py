def test_build_command_matches_the_spec_flag_set(itest_conftest):
    caps = itest_conftest.TIER_CAPS["gates"]
    cmd = itest_conftest.build_command("/relay:verify --engine in-session",
                                       "/wt/plugins/relay", caps)
    assert cmd[:3] == ["claude", "-p", "/relay:verify --engine in-session"]
    joined = " ".join(cmd)
    assert "--plugin-dir /wt/plugins/relay" in joined
    assert "--output-format stream-json --verbose" in joined
    assert "--permission-mode bypassPermissions" in joined
    assert "--strict-mcp-config" in joined
    assert "--max-budget-usd 1" in joined
    # --max-turns is registered but hidden from `claude --help`; the parse-time probe in
    # test_cli_flags_supported.py is what proves it exists. It is the real ceiling while
    # C2 leaves --max-budget-usd enforcement unsettled on a subscription login.
    assert "--max-turns 40" in joined
    # C1: global CLAUDE.md noise is accepted day one; the flag stays off.
    assert "--setting-sources" not in joined


def test_tier_caps_values(itest_conftest):
    caps = itest_conftest.TIER_CAPS
    assert caps["gates"] == {"budget_usd": 1, "max_turns": 40, "wall_clock": 600}
    assert caps["e2e"] == {"budget_usd": 10, "max_turns": 300, "wall_clock": 7200}
