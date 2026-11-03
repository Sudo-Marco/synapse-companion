from synapse_pet.runtime.engine import PetEngine

def test_engine_uses_opt_in_sensors_tools_and_restores(tmp_path):
    engine = PetEngine(seed=19, neurons=600, data_dir=tmp_path)
    assert all(not engine.sensor_manager.sensors[name].enabled
               for name in engine.sensor_manager.NAMES)
    assert "tool:pausa" in engine.network.output_groups
    engine.tick({"input_rate": .4, "window_category": "codigo", "activity": .2, "hour": .5})
    assert engine.network.tick_count == 25
    result = engine.execute_tool("pausa")
    assert result["status"] == "success"
    note = engine.execute_tool("anotar", {"text": "local note"})
    assert note["status"] == "success"
    assert engine.undo_last()["status"] == "undone"
    found = engine.registry.get("buscar_notas").run({"query": "local note"})
    assert found["notes"] == []
    blocked = engine.execute_tool("rodar_comando_permitido", {"executable": "cmd.exe"})
    assert blocked["status"] == "confirmation_required"
    engine.save()

    resumed = PetEngine(data_dir=tmp_path)
    assert resumed.network.tick_count == engine.network.tick_count
    assert resumed.selector.preferences[("outro", "pausa")] > 0
    assert resumed.network.population.size == engine.network.population.size
