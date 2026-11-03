import json
from pathlib import Path

from synapse_pet.sim.determinism import reference_snapshot


ROOT = Path(__file__).resolve().parents[1]


def test_fixed_seed_matches_frozen_snn_reference():
    reference = json.loads(
        (ROOT / "benchmarks" / "results" / "snn_determinism_reference.json")
        .read_text(encoding="utf-8")
    )
    assert reference_snapshot() == reference
