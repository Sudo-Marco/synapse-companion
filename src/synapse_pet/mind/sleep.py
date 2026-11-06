from __future__ import annotations
from dataclasses import dataclass
import hashlib
import numpy as np
from ..core.network import SpikingNetwork
from ..core.plasticity import RewardSTDP
from ..core.neuromodulators import Neuromodulators
from .episodic_memory import EpisodicMemory

@dataclass
class SleepConsolidator:
    sleep_after_s: float = 1800.0
    idle_s: float = 0.0
    sleeping: bool = False
    max_replay_episodes: int = 12
    replay_recent_fraction: float = 0.05
    regrow_fraction: float = 0.0001
    replay_enabled: bool = False
    replay_noise: float = 0.005
    replay_steps: int = 2

    def update(self, dt_s: float, active: bool, on_ac_power: bool = False) -> bool:
        self.idle_s = 0.0 if active else self.idle_s + dt_s
        self.sleeping = self.idle_s >= self.sleep_after_s
        return self.sleeping

    def consolidate(self, network: SpikingNetwork, memory: EpisodicMemory,
                     learners: dict[str, RewardSTDP], modulators: Neuromodulators) -> int:
        """Replay a bounded number of safe episodes, prune weak edges, and regrow a few."""
        candidates = getattr(memory, "replay_candidates", memory.top_rpe)
        episodes = (candidates(self.max_replay_episodes,
                               self.replay_recent_fraction)
                    if self.replay_enabled else [])
        dt_s = network.dt_ms / 1000.0
        active_context = network._active_output_context
        try:
            for context, action, rpe_value, _timestamp, _emotion in reversed(episodes):
                context_digest = hashlib.blake2b(
                    str(context).encode("utf-8"), digest_size=16).hexdigest()
                network.activate_existing_output_context(context_digest)
                sensor_index_digest = hashlib.blake2b(
                    str(context).encode("utf-8"), digest_size=4).digest()
                sensor_index = int.from_bytes(sensor_index_digest, "little") % network.n_sensor
                current = np.zeros(network.n_sensor, dtype=np.float32)
                current[sensor_index] = 1.0
                for _ in range(max(1, int(self.replay_steps))):
                    replay_input = current.copy()
                    if self.replay_noise > 0.0:
                        replay_input += network.rng.normal(
                            0.0, self.replay_noise, network.n_sensor).astype(np.float32)
                    spikes = network.step(np.clip(replay_input, 0.0, 1.5))
                    h = slice(network.hidden_start, network.output_start)
                    out = slice(network.output_start, network.output_start + network.hidden_to_output.n_post)
                    learners["sensor_hidden"].mark(network.sensor_to_hidden, spikes[:network.n_sensor], spikes[h], dt_s)
                    learners["recurrent"].mark(network.recurrent, spikes[h], spikes[h], dt_s)
                    learners["hidden_output"].mark(network.hidden_to_output, spikes[h], spikes[out], dt_s)
                dopamine = float(np.clip(float(rpe_value), -1.0, 1.0)) * 0.1
                learners["sensor_hidden"].apply_reward(network.sensor_to_hidden, dopamine)
                learners["recurrent"].apply_reward(network.recurrent, dopamine)
                tool_group = network.output_groups.get(f"tool:{action}") if action else None
                if tool_group is not None:
                    output_indices = (tool_group - network.output_start).astype(np.int32)
                    learners["hidden_output"].apply_action_credit(
                        network.hidden_to_output, dopamine, output_indices,
                        spikes[h].astype(np.float32),
                        learning_rate=learners["hidden_output"].learning_rate)
                else:
                    learners["hidden_output"].apply_reward(
                        network.hidden_to_output, dopamine)
        finally:
            if episodes:
                if active_context is None:
                    network.use_base_output_context()
                else:
                    network.activate_existing_output_context(active_context)
        projections = (network.sensor_to_hidden, network.recurrent,
                       network.hidden_to_output)
        for projection in projections:
            if projection is network.hidden_to_output:
                # Every contextual readout shares this CSR topology. Keep an
                # edge if any saved projection still uses it, then apply the
                # same mask to base and contextual weight vectors.
                keep = np.abs(network._base_hidden_output_weights) >= 1e-5
                for context_state in network.context_output_weights.values():
                    keep |= np.abs(context_state.weights) >= 1e-5
            else:
                keep = np.abs(projection.weights) >= 1e-5
            if not np.all(keep):
                projection.pre = projection.pre[keep]
                projection.post = projection.post[keep]
                projection.weights = projection.weights[keep]
                projection.rebuild()
                if projection is network.hidden_to_output:
                    network._base_hidden_output_weights = (
                        network._base_hidden_output_weights[keep].copy())
                    for context_state in network.context_output_weights.values():
                        context_state.weights = context_state.weights[keep].copy()
                    active = network.context_output_weights.get(
                        network._active_output_context or "")
                    projection.bind_weights(
                        active.weights if active is not None
                        else network._base_hidden_output_weights)
        recurrent = network.recurrent
        count = max(1, int(len(recurrent.weights) * self.regrow_fraction))
        pre = network.rng.integers(0, recurrent.n_pre, count, dtype=np.int32)
        post = network.rng.integers(0, recurrent.n_post, count, dtype=np.int32)
        weights = network.rng.uniform(0.02, 0.04, count).astype(np.float32) * recurrent.source_sign[pre]
        recurrent.pre = np.concatenate((recurrent.pre, pre))
        recurrent.post = np.concatenate((recurrent.post, post))
        recurrent.weights = np.concatenate((recurrent.weights, weights))
        recurrent.rebuild()
        modulators.stress *= 0.5
        modulators.energy = min(1.0, modulators.energy + 0.15)
        return len(episodes)
