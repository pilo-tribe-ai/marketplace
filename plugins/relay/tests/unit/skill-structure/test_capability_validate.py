import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
TEST_JS = PLUGIN_ROOT / "scripts" / "capability-validate.test.js"

def test_capability_validate_node_suite_passes():
    result = subprocess.run(
        ["node", "--test", str(TEST_JS)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"node --test failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
