import numpy as np
from synapse_pet.core.homeostasis import Homeostasis
from synapse_pet.core.neurons import LIFPopulation

def test_homeostasis_corrects_silence_and_high_activity():
    p = LIFPopulation(10)
    homeostasis = Homeostasis(window_s=1.0)
    quiet = np.zeros(10, dtype=bool)
    events = []
    for _ in range(50):
        events.extend(homeostasis.update(p, quiet, .02))
    assert "silencio_detectado" in events
    low_threshold = p.threshold
    active = np.ones(10, dtype=bool)
    events = []
    for _ in range(50):
        events.extend(homeostasis.update(p, active, .02))
    assert "epilepsia_detectada" in events
    assert p.threshold > low_threshold
