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
        # Optional output competition. It changes only currents when explicitly
        # enabled; the shipped configuration keeps the historical path intact.
        self.tool_output_inhibition_enabled = False
        self.tool_output_inhibition_strength = 0.35
        self.tool_output_inhibition_interval_steps = 5
        self.n_sensor = int(total_neurons * 0.16)
        self.n_hidden = int(total_neurons * 0.64)
        self.hidden_start = self.n_sensor
        self.output_start = self.hidden_start + self.n_hidden
        self.n_output = total_neurons - self.n_sensor - self.n_hidden
        self.population = LIFPopulation(total_neurons)
        # Scratch storage owned by the single thread that advances this network.
        # It is resized lazily after dynamic tool groups or population growth.
        self._current_buffer = np.zeros(total_neurons, dtype=np.float32)
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
        self._refresh_tool_output_indices()
        self.tick_count = 0

    def _refresh_tool_output_indices(self) -> None:
        groups = [indices - self.output_start
                  for name, indices in self.output_groups.items()
                  if name.startswith("tool:") and len(indices)]
        self._tool_output_local_indices = (
            np.stack(groups).astype(np.int32, copy=False) if groups
            else np.empty((0, self.tool_group_size), dtype=np.int32))
        self._tool_output_slice: tuple[int, int] | None = None
        if groups:
            first = int(self._tool_output_local_indices[0, 0])
            expected = np.arange(first, first + len(groups) * self.tool_group_size,
                                 dtype=np.int32).reshape(-1, self.tool_group_size)
            if np.array_equal(self._tool_output_local_indices, expected):
                self._tool_output_slice = (first, len(groups))

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
        self._refresh_tool_output_indices()
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

    def _apply_tool_output_inhibition(self,
                                      output_current: NDArray[np.float32]) -> None:
        """Suppress non-winning tool groups without changing the LIF topology."""
        descriptor = self._tool_output_slice
        if descriptor is None or descriptor[1] < 2:
            return
        first, count = descriptor
        grouped_current = output_current[
            first:first + count * self.tool_group_size].reshape(
                count, self.tool_group_size)
        scores = np.mean(grouped_current, axis=1, dtype=np.float32)
        winner = int(np.argmax(scores))
        winning_score = np.maximum(np.float32(0.0), scores[winner])
        strength = np.float32(max(0.0, self.tool_output_inhibition_strength))
        inhibition = np.maximum(np.float32(0.0), winning_score - scores) * strength
        inhibition[winner] = np.float32(0.0)
        grouped_current -= inhibition[:, None]

    def step(self, sensor_current: NDArray[np.float32] | None = None) -> NDArray[np.bool_]:
        n = self.population.size
        current = self._current_buffer
        if current.shape != (n,):
            current = np.zeros(n, dtype=np.float32)
            self._current_buffer = current
        else:
            current.fill(0.0)
        if sensor_current is not None:
            if len(sensor_current) != self.n_sensor:
                raise ValueError("sensor_current length does not match sensory population")
            current[:self.n_sensor] += sensor_current
        spikes = self.population.spikes
        h = slice(self.hidden_start, self.output_start)
        current[h] += (self.sensor_to_hidden.currents(spikes[:self.n_sensor])
                       * np.float32(self.synaptic_gain))
        current[h] += self.recurrent.currents(spikes[h]) * np.float32(self.synaptic_gain)
        output_current = self.hidden_to_output.currents(spikes[h]) * np.float32(
            self.synaptic_gain)
        if (self.tool_output_inhibition_enabled
                and self.tick_count % max(1, int(
                    self.tool_output_inhibition_interval_steps)) == 0):
            self._apply_tool_output_inhibition(output_current)
        current[self.output_start:self.output_start + self.hidden_to_output.n_post] += output_current
        out = self.population.step(current, self.dt_ms, self.rng, self.noise,
                                   gain=1.0 + 0.5 * getattr(self, "stress", 0.0))
        self.tick_count += 1
        return out

    def add_input_spikes(self, spikes: NDArray[np.bool_]) -> None:
        if len(spikes) != self.n_sensor:
            raise ValueError("sensory spike vector length mismatch")
        self.population.spikes[:self.n_sensor] = spikes

    def grow_population(self, target_neurons: int, seed: int = 41) -> "SpikingNetwork":
        """Safely expand the network population to target_neurons, preserving state, weights, and context readouts."""
        tool_output_inhibition_enabled = self.tool_output_inhibition_enabled
        tool_output_inhibition_strength = self.tool_output_inhibition_strength
        tool_output_inhibition_interval_steps = self.tool_output_inhibition_interval_steps
        tool_names = [key[5:] for key in self.output_groups if key.startswith("tool:")]
        tool_count = len(tool_names)
        tool_neurons = tool_count * self.tool_group_size
        old_base_total = self.population.size - tool_neurons

        if target_neurons < 50:
            raise ValueError("network requires at least 50 neurons")
        if target_neurons < old_base_total:
            raise ValueError(f"cannot shrink network from {old_base_total} to {target_neurons} neurons")
        if target_neurons == old_base_total:
            return self

        migration_rng = np.random.default_rng(seed)

        old_n_sensor = self.n_sensor
        old_n_hidden = self.n_hidden
        old_base_n_output = self.n_output - tool_neurons

        new_base_total = target_neurons
        new_n_sensor = int(new_base_total * 0.16)
        new_n_hidden = int(new_base_total * 0.64)
        new_base_n_output = new_base_total - new_n_sensor - new_n_hidden
        new_output_start = new_n_sensor + new_n_hidden
        new_n_output = new_base_n_output + tool_neurons
        new_total_pop = new_base_total + tool_neurons

        # 1. Expand LIF population while preserving states of existing neurons
        new_pop = LIFPopulation(
            new_total_pop,
            tau_m_ms=self.population.tau_m_ms,
            threshold=self.population.threshold,
            reset=self.population.reset,
            refractory_ms=self.population.refractory_ms,
            adaptive_increment=self.population.adaptive_increment,
            adaptive_tau_ms=self.population.adaptive_tau_ms,
        )
        for attr in ("voltage", "threshold_offset", "refractory", "spikes"):
            old_val = getattr(self.population, attr)
            new_val = getattr(new_pop, attr)
            # Sensors (indices 0..old_n_sensor)
            new_val[0:old_n_sensor] = old_val[0:old_n_sensor]
            # Hidden (shifted by new_n_sensor)
            new_val[new_n_sensor:new_n_sensor + old_n_hidden] = old_val[old_n_sensor:old_n_sensor + old_n_hidden]
            # Base output (shifted by new_output_start)
            new_val[new_output_start:new_output_start + old_base_n_output] = old_val[self.output_start:self.output_start + old_base_n_output]
            # Dynamic tools
            if tool_neurons > 0:
                new_val[new_base_total:new_base_total + tool_neurons] = old_val[old_base_total:old_base_total + tool_neurons]

        # 2. Hidden Dale signs: preserve old, deterministically sample new
        new_hidden_signs = np.where(migration_rng.random(new_n_hidden - old_n_hidden) < 0.8, 1.0, -1.0).astype(np.float32)
        new_full_hidden_sign = np.concatenate([self.hidden_sign, new_hidden_signs])

        # 3. sensor_to_hidden projection
        post1_loc, pre1_loc = np.nonzero(migration_rng.random((old_n_hidden, new_n_sensor - old_n_sensor)) < self.connectivity)
        post1 = post1_loc.astype(np.int32)
        pre1 = (pre1_loc + old_n_sensor).astype(np.int32)

        post2_loc, pre2_loc = np.nonzero(migration_rng.random((new_n_hidden - old_n_hidden, new_n_sensor)) < self.connectivity)
        post2 = (post2_loc + old_n_hidden).astype(np.int32)
        pre2 = pre2_loc.astype(np.int32)

        new_s2h_pre = np.concatenate([pre1, pre2])
        new_s2h_post = np.concatenate([post1, post2])
        new_s2h_w = migration_rng.uniform(0.02, 0.12, len(new_s2h_pre)).astype(np.float32)

        all_s2h_pre = np.concatenate([self.sensor_to_hidden.pre, new_s2h_pre])
        all_s2h_post = np.concatenate([self.sensor_to_hidden.post, new_s2h_post])
        all_s2h_w = np.concatenate([self.sensor_to_hidden.weights, new_s2h_w])
        new_s2h = SparseProjection(new_n_sensor, new_n_hidden, all_s2h_pre, all_s2h_post, all_s2h_w,
                                   np.ones(new_n_sensor, dtype=np.float32), name="sensor_hidden")

        # 4. recurrent projection
        post1_loc, pre1_loc = np.nonzero(migration_rng.random((old_n_hidden, new_n_hidden - old_n_hidden)) < self.connectivity)
        post1 = post1_loc.astype(np.int32)
        pre1 = (pre1_loc + old_n_hidden).astype(np.int32)

        post2_loc, pre2_loc = np.nonzero(migration_rng.random((new_n_hidden - old_n_hidden, new_n_hidden)) < self.connectivity)
        post2 = (post2_loc + old_n_hidden).astype(np.int32)
        pre2 = pre2_loc.astype(np.int32)

        new_rec_pre = np.concatenate([pre1, pre2])
        new_rec_post = np.concatenate([post1, post2])
        new_rec_w = migration_rng.uniform(0.02, 0.08, len(new_rec_pre)).astype(np.float32) * new_full_hidden_sign[new_rec_pre]

        all_rec_pre = np.concatenate([self.recurrent.pre, new_rec_pre])
        all_rec_post = np.concatenate([self.recurrent.post, new_rec_post])
        all_rec_w = np.concatenate([self.recurrent.weights, new_rec_w])
        new_rec = SparseProjection(new_n_hidden, new_n_hidden, all_rec_pre, all_rec_post, all_rec_w,
                                   new_full_hidden_sign, name="recurrent")

        # 5. hidden_to_output projection and context projections
        h2o_post_shifted = np.where(self.hidden_to_output.post >= old_base_n_output,
                                    self.hidden_to_output.post + (new_base_n_output - old_base_n_output),
                                    self.hidden_to_output.post).astype(np.int32)
        h2o_pre = self.hidden_to_output.pre.copy()

        postA_loc, preA_loc = np.nonzero(migration_rng.random((new_base_n_output - old_base_n_output, old_n_hidden)) < self.connectivity)
        postA = (postA_loc + old_base_n_output).astype(np.int32)
        preA = preA_loc.astype(np.int32)

        postB_loc, preB_loc = np.nonzero(migration_rng.random((new_n_output, new_n_hidden - old_n_hidden)) < self.connectivity)
        postB = postB_loc.astype(np.int32)
        preB = (preB_loc + old_n_hidden).astype(np.int32)

        new_h2o_pre = np.concatenate([preA, preB])
        new_h2o_post = np.concatenate([postA, postB])
        new_h2o_w = migration_rng.uniform(0.02, 0.12, len(new_h2o_pre)).astype(np.float32) * new_full_hidden_sign[new_h2o_pre]

        all_h2o_pre = np.concatenate([h2o_pre, new_h2o_pre])
        all_h2o_post = np.concatenate([h2o_post_shifted, new_h2o_post])
        all_h2o_base_w = np.concatenate([self._base_hidden_output_weights, new_h2o_w])

        try:
            from scipy.sparse import csr_matrix
            use_csr = True
        except ImportError:
            use_csr = False

        if use_csr:
            m_base = csr_matrix((all_h2o_base_w, (all_h2o_post, all_h2o_pre)), shape=(new_n_output, new_n_hidden), dtype=np.float32)
            m_base.sum_duplicates()
            m_base.sort_indices()
            new_h2o = SparseProjection(
                new_n_hidden, new_n_output,
                m_base.indices.astype(np.int32, copy=False),
                np.repeat(np.arange(new_n_output, dtype=np.int32), np.diff(m_base.indptr)).astype(np.int32, copy=False),
                m_base.data, new_full_hidden_sign, name="hidden_output"
            )
            self._base_hidden_output_weights = m_base.data.copy()

            for ctx_id, ctx_state in self._context_output_weights.items():
                all_ctx_w = np.concatenate([ctx_state.weights, new_h2o_w])
                m_ctx = csr_matrix((all_ctx_w, (all_h2o_post, all_h2o_pre)), shape=(new_n_output, new_n_hidden), dtype=np.float32)
                m_ctx.sum_duplicates()
                m_ctx.sort_indices()
                ctx_state.weights = m_ctx.data.astype(np.float32, copy=False)
        else:
            new_h2o = SparseProjection(new_n_hidden, new_n_output, all_h2o_pre, all_h2o_post, all_h2o_base_w,
                                       new_full_hidden_sign, name="hidden_output")
            self._base_hidden_output_weights = all_h2o_base_w.copy()
            for ctx_id, ctx_state in self._context_output_weights.items():
                ctx_state.weights = np.concatenate([ctx_state.weights, new_h2o_w]).astype(np.float32, copy=False)

        # 6. Apply state and rewire references
        self.population = new_pop
        self.n_sensor = new_n_sensor
        self.n_hidden = new_n_hidden
        self.hidden_start = new_n_sensor
        self.output_start = new_output_start
        self.n_output = new_n_output
        self.hidden_sign = new_full_hidden_sign
        self.sensor_to_hidden = new_s2h
        self.recurrent = new_rec
        self.hidden_to_output = new_h2o

        if self._active_output_context in self._context_output_weights:
            self.hidden_to_output.bind_weights(self._context_output_weights[self._active_output_context].weights)
        else:
            self._active_output_context = None
            self.hidden_to_output.bind_weights(self._base_hidden_output_weights)

        # 7. Update output groups
        for i, name in enumerate(("feliz", "sonolento", "curioso", "assustado", "atencao", "brincando")):
            self.output_groups[name] = np.array([self.output_start + i % max(1, self.n_output)], dtype=np.int32)
        self.initiative_index = self.output_start + min(6, self.n_output - 1)
        self.output_groups["iniciativa"] = np.array([self.initiative_index], dtype=np.int32)
        for j, tool_name in enumerate(tool_names):
            key = f"tool:{tool_name}"
            ids = np.arange(new_base_total + j * self.tool_group_size,
                            new_base_total + (j + 1) * self.tool_group_size, dtype=np.int32)
            self.output_groups[key] = ids

        self._refresh_tool_output_indices()

        self.tool_output_inhibition_enabled = tool_output_inhibition_enabled
        self.tool_output_inhibition_strength = tool_output_inhibition_strength
        self.tool_output_inhibition_interval_steps = tool_output_inhibition_interval_steps

        return self

    def dale_is_respected(self) -> bool:
        return bool(np.all(self.recurrent.weights * self.hidden_sign[self.recurrent.pre] >= -1e-7)
                    and np.all(self.hidden_to_output.weights * self.hidden_sign[self.hidden_to_output.pre] >= -1e-7))


def grow_population(network: SpikingNetwork, target_neurons: int, seed: int = 41) -> SpikingNetwork:
    """Safely grow a SpikingNetwork population."""
    return network.grow_population(target_neurons, seed=seed)


def _merge_projection(
    old_proj: SparseProjection,
    n_pre_new: int,
    n_post_new: int,
    connectivity: float,
    rng: np.random.Generator,
    scale: float,
    source_sign_new: NDArray[np.float32] | None = None,
    post_shift: int = 0,
    post_split: int = 0,
    name: str = "projection",
) -> SparseProjection:
    """Helper to merge and expand a sparse projection."""
    signs = np.ones(n_pre_new, dtype=np.float32) if source_sign_new is None else source_sign_new.astype(np.float32)
    post_shifted = old_proj.post.copy()
    if post_shift > 0 and post_split > 0:
        post_shifted = np.where(post_shifted >= post_split, post_shifted + post_shift, post_shifted).astype(np.int32)

    old_n_pre = old_proj.n_pre
    old_n_post = old_proj.n_post

    if post_shift > 0 and post_split > 0:
        postA_loc, preA_loc = np.nonzero(rng.random((n_post_new - old_n_post, old_n_pre)) < connectivity)
        postA = (postA_loc + post_split).astype(np.int32)
        preA = preA_loc.astype(np.int32)

        postB_loc, preB_loc = np.nonzero(rng.random((n_post_new, n_pre_new - old_n_pre)) < connectivity)
        postB = postB_loc.astype(np.int32)
        preB = (preB_loc + old_n_pre).astype(np.int32)
        new_pre = np.concatenate([preA, preB])
        new_post = np.concatenate([postA, postB])
    else:
        post1_loc, pre1_loc = np.nonzero(rng.random((old_n_post, n_pre_new - old_n_pre)) < connectivity)
        post1 = post1_loc.astype(np.int32)
        pre1 = (pre1_loc + old_n_pre).astype(np.int32)

        post2_loc, pre2_loc = np.nonzero(rng.random((n_post_new - old_n_post, n_pre_new)) < connectivity)
        post2 = (post2_loc + old_n_post).astype(np.int32)
        pre2 = pre2_loc.astype(np.int32)
        new_pre = np.concatenate([pre1, pre2])
        new_post = np.concatenate([post1, post2])

    new_w = rng.uniform(0.02, scale, len(new_pre)).astype(np.float32) * signs[new_pre]
    all_pre = np.concatenate([old_proj.pre, new_pre])
    all_post = np.concatenate([post_shifted, new_post])
    all_w = np.concatenate([old_proj.weights, new_w])
    return SparseProjection(n_pre_new, n_post_new, all_pre, all_post, all_w, signs, name=name)
