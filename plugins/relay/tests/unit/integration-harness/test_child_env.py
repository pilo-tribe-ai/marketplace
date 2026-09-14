def test_child_env_scrubs_relay_and_claude_but_keeps_home(itest_conftest):
    base = {
        "HOME": "/real/home",
        "PATH": "/usr/bin",
        "RELAY_ENGINE": "acpx",
        "RELAY_VERIFY_ROUNDS": "3",
        "CLAUDECODE": "1",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
        "UNRELATED": "keep-me",
    }
    env = itest_conftest.child_env(base)
    assert env["HOME"] == "/real/home"
    assert env["PATH"] == "/usr/bin"
    assert env["UNRELATED"] == "keep-me"
    assert not any(k.startswith("RELAY_") for k in env)
    assert "CLAUDECODE" not in env
    assert not any(k.startswith("CLAUDE_CODE_") for k in env)
