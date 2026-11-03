import pytest
from synapse_pet.tools.manifest import ToolManifest
from synapse_pet.tools.permissions import PermissionManager
from synapse_pet.tools.sandbox import Sandbox
from synapse_pet.tools.builtin.basic import open_url

def test_high_risk_requires_explicit_confirmation():
    pm = PermissionManager(); tool = ToolManifest("cmd", "", "high", ())
    assert not pm.authorize(tool)
    assert pm.authorize(tool, explicit=True)

def test_medium_requires_acceptance_and_auto_quota():
    pm = PermissionManager(max_automatic_per_hour=1)
    medium = ToolManifest("folder", "", "medium", ())
    low = ToolManifest("status", "", "low", ())
    assert not pm.authorize(medium)
    assert pm.authorize(medium, accepted=True)
    assert pm.authorize(low, now=100)
    assert not pm.authorize(low, now=101)

def test_open_url_requires_user_action():
    import pytest
    with pytest.raises(PermissionError):
        open_url({"url": "https://example.com"})
    with pytest.raises(ValueError):
        open_url({"url": "file:///secret"}, explicit_user_action=True)

def test_sandbox_blocks_unlisted_paths_and_commands(tmp_path):
    sandbox = Sandbox([str(tmp_path)], [])
    assert sandbox.path_allowed(tmp_path / "child")
    assert not sandbox.path_allowed(tmp_path.parent)
    with pytest.raises(PermissionError):
        sandbox.run_command("cmd.exe", ["/c", "echo hi"])
