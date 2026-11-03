from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from .neurons import LIFPopulation
from .synapses import SparseProjection


@dataclass
class ContextOutputWeights:
    """Lazy per-context readout weights on a shared sparse topology."""
    signature: NDArray[np.float32]
    weights: NDArray[np.float32]
    last_used: int
    reused_from: str | None = None


class SpikingNetwork:
    """Small CPU-only SNN with sparse vectorized projections and Dale signs."""
    def __init__(self, total_neurons: int = 600, connectivity: float = 0.10,
                 dt_ms: float = 2.0, seed: int = 41, noise: float = 0.015,
                 tool_group_size: int = 8, synaptic_gain: float = 1.0) -> None:
        if total_neurons < 50:
            raise ValueError("network requires at least 50 neurons")
        self.rng = np.random.default_rng(seed)
        self.dt_ms, self.noise, self.connectivity = dt_ms, noise, connectivity
        self.synaptic_gain = max(0.0, float(synaptic_gain))
        self.n_sensor = int(total_neurons * 0.16)
        self.n_hidden = int(total_neurons * 0.64)
        self.hidden_start = self.n_sensor
        self.output_start = self.hidden_start + self.n_hidden
        self.n_output = total_neurons - self.n_sensor - self.n_hidden
        self.population = LIFPopulation(total_neurons)
        self.hidden_sign = np.where(self.rng.random(self.n_hidden) < 0.8, 1.0, -1.0).astype(np.float32)
        self.sensor_to_hidden = SparseProjection.random(self.n_sensor, self.n_hidden, connectivity,
                                                       self.rng, scale=0.12, name="sensor_hidden")
        self.recurrent = SparseProjection.random(self.n_hidden, self.n_hidden, connectivity,
                                                  self.rng, source_sign=self.hidden_sign, scale=0.08, name="recurrent")
        self.hidden_to_output = SparseProjection.random(self.n_hidden, self.n_output, connectivity,
                                                         self.rng, source_sign=self.hidden_sign, scale=0.12, name="hidden_output")
        self._base_hidden_output_weights = self.hidden_to_output.weights.copy()
        self._context_output_weights: dict[str, ContextOutputWeights] = {}
        self._active_output_context: str | None = None
        self._context_use_clock = 0
        self.max_context_projections = 8
        self.context_similarity_threshold = 0.85
        self.tool_group_size = tool_group_size
        self.output_groups: dict[str, NDArray[np.int32]] = {}
        for i, name in enumerate(("feliz", "sonolento", "curioso", "assustado", "atencao", "brincando")):
            self.output_groups[name] = np.array([self.output_start + i % max(1, self.n_output)], dtype=np.int32)
        self.initiative_index = self.output_start + min(6, self.n_output - 1)
        self.output_groups["iniciativa"] = np.array([self.initiative_index], dtype=np.int32)
        self.tick_count = 0

    def add_tool_group(self, name: str) -> NDArray[np.int32]:
        key = f"tool:{name}"
        if key in self.output_groups:
            return self.output_groups[key]
        old_size = len(self.population.voltage)
        old_targets = self.hidden_to_output.n_post
        add = self.tool_group_size
        # Grow output rows and connect them sparsely from the existing hidden layer.
        local_post, pre = np.nonzero(self.rng.random((add, self.n_hidden)) < self.connectivity)
        signs = self.hidden_sign[pre]
        weights = self.rng.uniform(0.02, 0.12, len(pre)).astype(np.float32) * signs
        projection = self.hidden_to_output
        projection.pre = np.concatenate([projection.pre, pre.astype(np.int32)])
        projection.post = np.concatenate([projection.post, (local_post + old_targets).astype(np.int32)])
        projection.weights = np.concatenate([projection.weights, weights])
        projection.n_post += add
        projection.rebuild()
        self._base_hidden_output_weights = np.concatenate(
            [self._base_hidden_output_weights, weights]).astype(np.float32, copy=False)
        for context_state in self._context_output_weights.values():
            context_state.weights = np.concatenate(
                [context_state.weights, weights]).astype(np.float32, copy=False)
        if self._active_output_context in self._context_output_weights:
            projection.bind_weights(
                self._context_output_weights[self._active_output_context].weights)
        else:
            self._active_output_context = None
            projection.bind_weights(self._base_hidden_output_weights)
        for attr, fill, dtype in (("voltage", 0, np.float32), ("threshold_offset", 0, np.float32),
                                  ("refractory", 0, np.float32), ("spikes", False, np.bool_)):
            setattr(self.population, attr, np.concatenate([getattr(self.population, attr), np.full(add, fill, dtype=dtype)]))
        self.population.size += add
        self.n_output += add
        ids = np.arange(old_size, old_size + add, dtype=np.int32)
        self.output_groups[key] = ids
        return ids

    @property
    def context_output_weights(self) -> dict[str, ContextOutputWeights]:
        return self._context_output_weights

    def configure_context_output_projections(self, max_contexts: int = 8,
                                             similarity_threshold: float = 0.85) -> None:
        self.max_context_projections = max(1, int(max_contexts))
        self.context_similarity_threshold = float(np.clip(similarity_threshold, 0.0, 1.0))
        while len(self._context_output_weights) > self.max_context_projections:
            least_used = min(self._context_output_weights,
                             key=lambda key: self._context_output_weights[key].last_used)
            if self._active_output_context == least_used:
                self.use_base_output_context()
            del self._context_output_weights[least_used]

    def _touch_context(self, context_id: str) -> ContextOutputWeights:
        state = self._context_output_weights[context_id]
        self._context_use_clock += 1
        state.last_used = self._context_use_clock
        return state

    def activate_output_context(self, context_id: str,
                                signature: NDArray[np.float32]) -> str:
        """Activate or lazily create a readout; return its source ('base' or context id)."""
        context_id = str(context_id)
        if context_id in self._context_output_weights:
            state = self._touch_context(context_id)
        else:
            if len(self._context_output_weights) >= self.max_context_projections:
                least_used = min(self._context_output_weights,
                                 key=lambda key: self._context_output_weights[key].last_used)
                if self._active_output_context == least_used:
                    self.use_base_output_context()
                del self._context_output_weights[least_used]
            signature = np.asarray(signature, dtype=np.float32).reshape(-1).copy()
            if not np.all(np.isfinite(signature)):
                raise ValueError("context signature must contain finite values")
            reused_from: str | None = None
            initial_weights = self._base_hidden_output_weights
            signature_norm = float(np.linalg.norm(signature))
            best_similarity = -1.0
            if signature_norm > 1e-12:
                for known_id, known in self._context_output_weights.items():
                    if known.signature.shape != signature.shape:
                        continue
                    known_norm = float(np.linalg.norm(known.signature))
                    if known_norm <= 1e-12:
                        continue
                    similarity = float(np.dot(signature, known.signature)
                                       / (signature_norm * known_norm))
                    if similarity > best_similarity:
                        best_similarity, reused_from = similarity, known_id
                if best_similarity < self.context_similarity_threshold:
                    reused_from = None
            if reused_from is not None:
                initial_weights = self._context_output_weights[reused_from].weights
            self._context_use_clock += 1
            state = ContextOutputWeights(signature, initial_weights.copy(),
                                         self._context_use_clock, reused_from)
            self._context_output_weights[context_id] = state
        self.hidden_to_output.bind_weights(state.weights)
        self._active_output_context = context_id
        return state.reused_from or "base"

    def activate_existing_output_context(self, context_id: str) -> bool:
        """Switch to an allocated context without allocating on reward paths."""
        context_id = str(context_id)
        state = self._context_output_weights.get(context_id)
        if state is None:
            self.use_base_output_context()
            return False
        state = self._touch_context(context_id)
        self.hidden_to_output.bind_weights(state.weights)
        self._active_output_context = context_id
        return True

    def use_base_output_context(self) -> None:
        self.hidden_to_output.bind_weights(self._base_hidden_output_weights)
        self._active_output_context = None

    def restore_base_output_weights(self, weights: NDArray[np.float32]) -> None:
        weights = np.asarray(weights, dtype=np.float32).reshape(-1).copy()
        if weights.shape != self.hidden_to_output.weights.shape:
            raise ValueError("base output weights do not match the sparse topology")
        self._base_hidden_output_weights = weights
        self._context_output_weights.clear()
        self._active_output_context = None
        self.hidden_to_output.bind_weights(self._base_hidden_output_weights)

    def restore_context_output_weights(self, context_id: str,
                                       signature: NDArray[np.float32],
                                       weights: NDArray[np.float32], last_used: int,
                                       reused_from: str | None = None) -> None:
        signature = np.asarray(signature, dtype=np.float32).reshape(-1).copy()
        weights = np.asarray(weights, dtype=np.float32).reshape(-1).copy()
        if weights.shape != self._base_hidden_output_weights.shape:
            raise ValueError("context output weights do not match the sparse topology")
        if not np.all(np.isfinite(signature)) or not np.all(np.isfinite(weights)):
            raise ValueError("context projection contains non-finite values")
        used = max(0, int(last_used))
        self._context_output_weights[str(context_id)] = ContextOutputWeights(
            signature, weights, used, reused_from)
        self._context_use_clock = max(self._context_use_clock, used)

    def step(self, sensor_current: NDArray[np.float32] | None = None) -> NDArray[np.bool_]:
        n = self.population.size
        current = np.zeros(n, dtype=np.float32)
        if sensor_current is not None:
            if len(sensor_current) != self.n_sensor:
                raise ValueError("sensor_current length does not match sensory population")
            current[:self.n_sensor] += sensor_current
        spikes = self.population.spikes
        h = slice(self.hidden_start, self.output_start)
        current[h] += (self.sensor_to_hidden.currents(spikes[:self.n_sensor])
                       * np.float32(self.synaptic_gain))
        current[h] += self.recurrent.currents(spikes[h]) * np.float32(self.synaptic_gain)
        current[self.output_start:self.output_start + self.hidden_to_output.n_post] += (
            self.hidden_to_output.currents(spikes[h]) * np.float32(self.synaptic_gain))
        out = self.population.step(current, self.dt_ms, self.rng, self.noise,
                                   gain=1.0 + 0.5 * getattr(self, "stress", 0.0))
        self.tick_count += 1
        return out

    def add_input_spikes(self, spikes: NDArray[np.bool_]) -> None:
        if len(spikes) != self.n_sensor:
            raise ValueError("sensory spike vector length mismatch")
        self.population.spikes[:self.n_sensor] = spikes

    def dale_is_respected(self) -> bool:
        return bool(np.all(self.recurrent.weights * self.hidden_sign[self.recurrent.pre] >= -1e-7)
                    and np.all(self.hidden_to_output.weights * self.hidden_sign[self.hidden_to_output.pre] >= -1e-7))
