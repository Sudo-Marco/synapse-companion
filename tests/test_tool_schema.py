from __future__ import annotations

import math
import pytest

from synapse_pet.mind.action_selection import ActionCandidate
from synapse_pet.runtime.engine import PetEngine
from synapse_pet.tools.manifest import ToolManifest, ToolParameter, ToolParameterError


def test_manifest_applies_safe_defaults_and_checks_types_and_ranges():
    manifest = ToolManifest(
        "timer", "", "low", (),
        parameters={
            "minutes": ToolParameter(int, default=25, minimum=1, maximum=90),
            "label": ToolParameter(str, default="Foco", max_length=20),
        })

    assert manifest.prepare_parameters({}) == {"minutes": 25, "label": "Foco"}
    assert manifest.prepare_parameters({"minutes": 45}) == {
        "minutes": 45, "label": "Foco"}
    with pytest.raises(ToolParameterError):
        manifest.prepare_parameters({"minutes": True})
    with pytest.raises(ToolParameterError):
        manifest.prepare_parameters({"minutes": 0})
    with pytest.raises(ToolParameterError):
        manifest.prepare_parameters({"minutes": 25, "unexpected": 1})


def test_manifest_rejects_non_finite_and_boolean_numeric_values():
    manifest = ToolManifest(
        "numeric", "", "low", (),
        parameters={"value": ToolParameter((int, float), required=True)})

    assert manifest.prepare_parameters({"value": 2.5}) == {"value": 2.5}
    with pytest.raises(ToolParameterError):
        manifest.prepare_parameters({"value": True})
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ToolParameterError):
            manifest.prepare_parameters({"value": value})


def test_missing_required_parameters_prevent_tool_execution(tmp_path):
    called = False

    def run(_params):
        nonlocal called
        called = True
        return {"ok": True}

    engine = PetEngine(seed=73, data_dir=tmp_path)
    engine.register_tool(ToolManifest(
        "needs_input", "", "low", (), run=run,
        parameters={"value": ToolParameter(str, required=True)}))

    result = engine.execute_tool("needs_input", {})

    assert result["status"] == "configuration_required"
    assert result["missing"] == ("value",)
    assert not called


def test_exploration_without_allowed_folder_is_not_dispatched(tmp_path):
    engine = PetEngine(seed=74, data_dir=tmp_path)

    engine._dispatch_tool("resumo_arquivos_alterados", accepted=True)

    result = engine.action_results.get_nowait()
    assert result["status"] == "configuration_required"
    assert result["missing"] == ("folder",)


def test_missing_required_arguments_block_autonomous_proposal(tmp_path):
    engine = PetEngine(seed=741, data_dir=tmp_path)
    engine.autonomy_enabled = True
    engine.decide_action = lambda context: ActionCandidate(
        "resumo_arquivos_alterados", 1.0, "medium", context)
    engine.events.put({})

    engine._run_iteration()

    assert engine.proposals.empty()
    result = engine.action_results.get_nowait()
    assert result["status"] == "configuration_required"
    assert result["missing"] == ("folder",)


def test_missing_parameter_notice_uses_per_tool_cooldown(tmp_path):
    engine = PetEngine(seed=742, data_dir=tmp_path)
    engine._tool_config_notice_cooldown_s = 60.0

    engine._dispatch_tool("resumo_arquivos_alterados", accepted=True)
    result = engine.action_results.get_nowait()
    assert result["status"] == "configuration_required"
    assert result["missing"] == ("folder",)

    engine._dispatch_tool("resumo_arquivos_alterados", accepted=True)
    assert engine.action_results.empty()


def test_tool_failure_sets_cooldown_and_small_negative_reward(tmp_path):
    engine = PetEngine(seed=75, data_dir=tmp_path)

    def fail(_params):
        raise RuntimeError("private detail should not be surfaced")

    engine.register_tool(ToolManifest("flaky", "", "low", (), run=fail))
    with pytest.raises(RuntimeError):
        engine.execute_tool("flaky")

    assert engine._tool_cooldowns["flaky"] > 0
    assert engine._proposal_cooldowns["flaky"] >= engine._tool_cooldowns["flaky"]
    assert engine.affect_impulse < 0.0


def test_async_tool_failure_is_sanitized_for_ui(tmp_path):
    engine = PetEngine(seed=751, data_dir=tmp_path)
    engine._finish_tool({
        "name": "flaky", "context": "outro", "params": {},
        "error": RuntimeError("private detail must stay in the log"),
    })

    result = engine.action_results.get_nowait()
    assert result["operation"] == "tool"
    assert result["status"] == "error"
    assert result["error"] == "Falha em flaky: RuntimeError"
    assert "private detail" not in result["error"]
    assert engine.affect_impulse < 0.0
    assert engine._tool_cooldowns["flaky"] > 0.0
