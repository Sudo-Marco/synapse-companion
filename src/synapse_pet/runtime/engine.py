from __future__ import annotations
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import queue
import threading
import time
import numpy as np
from ..core.network import SpikingNetwork
from ..runtime.config import load_config, load_window_rules
from ..sensors.manager import SensorManager
from ..core.encoding import PopulationEncoder
from ..core.decoding import RateDecoder
from ..core.neuromodulators import Neuromodulators
from ..core.homeostasis import Homeostasis
from ..core.plasticity import RewardSTDP
from ..mind.emotions import EmotionState
from ..mind.personality import Personality
from ..mind.drives import Drives
from ..mind.sleep import SleepConsolidator
from ..mind.episodic_memory import EpisodicMemory
from ..mind.action_selection import ActionCandidate, ActionSelector
from ..tools.registry import ToolRegistry
from ..tools.permissions import PermissionManager
from ..tools.sandbox import Sandbox
from ..tools.manifest import ToolManifest
from ..tools.builtin.basic import builtin_tools
from .persistence import SnapshotStore
from .logging_db import ActionLog
from .scheduler import RuntimeScheduler
from .visual_state import VisualState

APP_DATA = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "synapse_pet"

class PetEngine:
    def __init__(self, seed: int | None = None, neurons: int | None = None, data_dir: Path = APP_DATA) -> None:
        self.data_dir = data_dir
        self.log_path = data_dir / "logs" / "synapse_pet.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(f"synapse_pet.runtime.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self._log_handler = RotatingFileHandler(
            self.log_path, maxBytes=1_000_000, backupCount=5,
            encoding="utf-8", delay=True)
        self._log_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(threadName)s %(message)s"))
        self.logger.addHandler(self._log_handler)
        self.config = load_config()
        network_config = self.config.get("network", {})
        self.runtime_config = self.config.get("runtime", {})
        self.visual_config = self.config.get("visual", {})
        self.learning_config = self.config.get("learning", {})
        self.plasticity_config = self.config.get("plasticity", {})
        self.context_projection_config = self.config.get("context_projections", {})
        self.interaction_config = self.config.get("interaction", {})
        self.curiosity_config = self.config.get("curiosity_novelty", {})
        self.affect_config = self.config.get("affect", {})
        self.mood_config = self.config.get("mood", {})
        self._mood_relax_fast_tau_s = float(self.mood_config.get(
            "relax_fast_tau_s", 240.0))
        self._mood_relax_slow_tau_s = float(self.mood_config.get(
            "relax_slow_tau_s", 1800.0))
        self._mood_slow_component_fraction = float(self.mood_config.get(
            "slow_component_fraction", 0.20))
        self._curiosity_impulse_tau_s = max(0.1, float(
            self.curiosity_config.get("impulse_tau_s", 2.5)))
        self._affect_impulse_tau_s = max(0.05, float(
            self.learning_config.get("affect_impulse_tau_s", 4.0)))
        self._affect_happiness_gain = float(
            self.learning_config.get("affect_happiness_gain", 0.10))
        self._curiosity_base = float(self.learning_config.get("curiosity_base", 0.25))
        self._curiosity_inactivity_gain = float(
            self.learning_config.get("curiosity_inactivity_gain", 0.40))
        self._curiosity_energy_gain = float(
            self.learning_config.get("curiosity_energy_gain", 0.15))
        self.reward_channels = self.config.get("reward_channels", {})
        seed = int(self.config.get("seed", 41) if seed is None else seed)
        neurons = int(network_config.get("neurons", 600) if neurons is None else neurons)
        self.store = SnapshotStore(data_dir / "creature")
        saved_state: dict[str, object] = {}
        if self.store.path.with_suffix(".json").exists():
            self.network, saved_state = self.store.load()
        else:
            self.network = SpikingNetwork(
                neurons, connectivity=float(network_config.get("recurrent_connectivity", .1)),
                dt_ms=float(network_config.get("dt_ms", 2.0)), seed=seed,
                noise=float(network_config.get("background_noise", .015)),
                tool_group_size=int(network_config.get("tool_group_size", 8)),
                synaptic_gain=float(network_config.get("synaptic_gain", 1.0)))
        # Apply active settings even when loading a snapshot created by an older config.
        self.network.synaptic_gain = max(0.0, float(network_config.get("synaptic_gain", 1.0)))
        self.network.configure_context_output_projections(
            max_contexts=int(self.context_projection_config.get("max_contexts", 8)),
            similarity_threshold=float(self.context_projection_config.get(
                "similarity_threshold", 0.85)))
        sensor_count = self.network.n_sensor
        group_size, remainder = divmod(sensor_count, 4)
        self.encoder = PopulationEncoder({
            name: group_size + int(index < remainder)
            for index, name in enumerate(
                ("input_rate", "window_category", "activity", "hour"))
        }, seed)
        self.registry = ToolRegistry()
        tool_config = self.config.get("tools", {})
        self.sandbox = Sandbox(tool_config.get("allowed_folders", []),
                               tool_config.get("allowed_commands", []),
                               tool_config.get("allowed_apps", []))
        sensor_config = self.config.get("privacy", {}).get("sensors", {})
        self.sensor_manager = SensorManager(data_dir, sensor_config, load_window_rules())
        for manifest in builtin_tools(data_dir, self.sandbox):
            self.registry.register(manifest)
            self.network.add_tool_group(manifest.name)
        self.decoder = RateDecoder(self.network.output_groups)
        self.learners = {"sensor_hidden": RewardSTDP(), "recurrent": RewardSTDP(),
                         "hidden_output": RewardSTDP()}
        self.learners["sensor_hidden"].initialize(self.network.sensor_to_hidden)
        self.learners["recurrent"].initialize(self.network.recurrent)
        self.learners["hidden_output"].initialize(self.network.hidden_to_output)
        self.neuromodulators = Neuromodulators()
        self.emotions = EmotionState()
        self.personality = Personality.seeded(seed)
        self.drives = Drives()
        self.selector = ActionSelector(
            feedback_rate=float(self.learning_config.get("action_preference_rate", 0.30)),
            neural_score_scale_hz=float(
                self.learning_config.get("neural_score_scale_hz", 15.0)))
        self._restore_mind(saved_state)
        self.sleep = SleepConsolidator(
            sleep_after_s=float(self.runtime_config.get("sleep_after_s", 1800)))
        self.homeostasis = Homeostasis()
        self.scheduler = RuntimeScheduler(
            active_timeout_s=float(self.runtime_config.get("active_timeout_s", 20)))
        self._autosave_interval_s = float(self.runtime_config.get("autosave_s", 60))
        self._last_autosave = time.monotonic()
        self.permissions = PermissionManager(
            max_automatic_per_hour=int(tool_config.get("max_automatic_per_hour", 6)))
        self.memory = EpisodicMemory(data_dir / "episodes.sqlite3")
        self.action_log = ActionLog(data_dir / "actions.sqlite3")
        self.events: queue.Queue[dict[str, object]] = queue.Queue()
        self.proposals: queue.Queue[ActionCandidate] = queue.Queue()
        self.visual_updates: queue.Queue[VisualState] = queue.Queue(maxsize=1)
        self.action_results: queue.Queue[dict[str, object]] = queue.Queue()
        self._pending_tools: dict[str, float] = {}
        self._proposal_cooldowns: dict[str, float] = {}
        self._last_auto_action: dict[str, float] = {}
        self._undo_stack: list[tuple[ToolManifest, dict[str, object]]] = []
        self.stop_event = threading.Event()
        self._watchdog_stop = threading.Event()
        self._thread_lock = threading.Lock()
        self._started = False
        self._sensors_started = False
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_timeout_s = max(1.0, float(
            self.runtime_config.get("watchdog_timeout_s", 3.0)))
        self._proposal_timeout_s = max(1.0, float(
            self.runtime_config.get("proposal_timeout_s", 120.0)))
        self._last_tick_at = time.monotonic()
        self._last_regime = "parado"
        self._stall_reported = False
        self._restart_requested = False
        self._last_runtime_error = ""
        self._save_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="synapse-pet-save")
        self._tool_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="synapse-pet-tool")
        self.last_rates: dict[str, float] = {}
        self._tick_spike_counts = np.zeros_like(self.network.population.spikes,
                                                dtype=np.float32)
        self._recent_hidden_activity: dict[str, np.ndarray] = {}
        self._last_hidden_activity = np.zeros(self.network.n_hidden, dtype=np.float32)
        self.affect_impulse = 0.0
        self.learning_rpe = 0.0
        self._last_curiosity_context: str | None = None
        self.curiosity_impulse = 0.0
        self._novelty_load: dict[tuple[str, str], float] = {}
        self._novelty_last_seen: dict[tuple[str, str], float] = {}
        self._rate_budgets: dict[str, deque[tuple[float, float]]] = {}
        self._last_rpe_is_deliberate = True
        self._non_deliberate_mood_budget_cap = max(
            0.0, float(self.affect_config.get("non_deliberate_mood_per_minute", 0.02)))
        self.simulation_cpu_seconds = 0.0
        self._thread: threading.Thread | None = None

    def _restore_mind(self, state: dict[str, object]) -> None:
        for key, cls in (("personality", Personality), ("neuromodulators", Neuromodulators),
                         ("emotions", EmotionState), ("drives", Drives)):
            values = state.get(key)
            if isinstance(values, dict):
                try:
                    setattr(self, key, cls(**values))
                except (TypeError, ValueError):
                    pass
        encoder_state = state.get("encoder_rng")
        if isinstance(encoder_state, dict):
            try:
                self.encoder.rng.bit_generator.state = encoder_state
            except (TypeError, ValueError):
                pass
        preferences = state.get("action_preferences", [])
        if isinstance(preferences, list):
            for item in preferences:
                if isinstance(item, dict) and "context" in item and "action" in item and "value" in item:
                    self.selector.preferences[(str(item["context"]), str(item["action"]))] = float(item["value"])
        self.selector.refusal_streak = int(state.get("refusal_streak", 0))
        self.selector.min_silence_s = float(state.get("min_silence_s", self.selector.min_silence_s))

    def _make_encoder(self) -> PopulationEncoder:
        group_size, remainder = divmod(self.network.n_sensor, 4)
        groups = {
            name: group_size + int(index < remainder)
            for index, name in enumerate(
                ("input_rate", "window_category", "activity", "hour"))
        }
        return PopulationEncoder(groups, int(self.config.get("seed", 41)))

    def _restore_last_snapshot(self) -> bool:
        """Reload the last atomically published checkpoint after a failed tick."""
        if not self.store.path.with_suffix(".json").exists():
            return False
        network, state = self.store.load()
        self.network = network
        network_config = self.config.get("network", {})
        self.network.synaptic_gain = max(
            0.0, float(network_config.get("synaptic_gain", 1.0)))
        self.network.configure_context_output_projections(
            max_contexts=int(self.context_projection_config.get("max_contexts", 8)),
            similarity_threshold=float(self.context_projection_config.get(
                "similarity_threshold", 0.85)))
        self.encoder = self._make_encoder()
        self.decoder = RateDecoder(self.network.output_groups)
        self.learners = {"sensor_hidden": RewardSTDP(), "recurrent": RewardSTDP(),
                         "hidden_output": RewardSTDP()}
        self.learners["sensor_hidden"].initialize(self.network.sensor_to_hidden)
        self.learners["recurrent"].initialize(self.network.recurrent)
        self.learners["hidden_output"].initialize(self.network.hidden_to_output)
        self.neuromodulators = Neuromodulators()
        self.emotions = EmotionState()
        self.personality = Personality.seeded(int(self.config.get("seed", 41)))
        self.drives = Drives()
        self.selector = ActionSelector(
            feedback_rate=float(self.learning_config.get("action_preference_rate", 0.30)),
            neural_score_scale_hz=float(
                self.learning_config.get("neural_score_scale_hz", 15.0)))
        self._restore_mind(state)
        self.homeostasis = Homeostasis()
        self.last_rates = {}
        self._tick_spike_counts = np.zeros_like(
            self.network.population.spikes, dtype=np.float32)
        self._recent_hidden_activity.clear()
        self._last_hidden_activity = np.zeros(self.network.n_hidden, dtype=np.float32)
        self.affect_impulse = 0.0
        self.curiosity_impulse = 0.0
        self.learning_rpe = self.neuromodulators.dopamine
        self._last_tick_at = time.monotonic()
        self._last_regime = "repouso"
        return True

    def _log_exception(self, message: str, exc: BaseException) -> None:
        self._last_runtime_error = f"{type(exc).__name__}: {exc}"
        self.logger.error(message, exc_info=(type(exc), exc, exc.__traceback__))

    def health_snapshot(self) -> dict[str, object]:
        """Small, read-only status for the main window and DEBUG panel."""
        now = time.monotonic()
        thread = self._thread
        alive = bool(thread and thread.is_alive())
        age = max(0.0, now - self._last_tick_at)
        stalled = self._started and age > self._watchdog_timeout_s
        status = "stalled" if stalled else ("running" if alive else "stopped")
        return {
            "status": status,
            "tick": int(self.network.tick_count),
            "regime": self._last_regime,
            "thread_alive": alive,
            "event_queue": self.events.qsize(),
            "proposal_queue": self.proposals.qsize(),
            "pending_proposals": len(self._pending_tools),
            "seconds_since_tick": age,
            "last_error": self._last_runtime_error,
            "log_path": str(self.log_path),
        }

    def proposal_is_pending(self, name: str) -> bool:
        return self._pending_tools.get(name, 0.0) > time.monotonic()

    @staticmethod
    def _context_projection_id(context: str) -> str:
        return hashlib.blake2b(context.encode("utf-8"), digest_size=16).hexdigest()

    def register_tool(self, manifest: ToolManifest) -> None:
        self.registry.register(manifest)
        self.network.add_tool_group(manifest.name)
        self.decoder = RateDecoder(self.network.output_groups)

    def tick(self, context: dict[str, object] | None = None, duration_ms: float = 50.0,
             active: bool | None = None, contacted: bool = False) -> dict[str, float]:
        context = context or {}
        category = context.get("window_category")
        if isinstance(category, str) and category:
            context_id = self._context_projection_id(category)
            if context_id in self.network.context_output_weights:
                self.network.activate_existing_output_context(context_id)
            else:
                self.network.activate_output_context(context_id, self.encoder.rates(context))
        else:
            self.network.use_base_output_context()
        encoded = self.encoder.encode(context, self.network.dt_ms) if context else np.zeros(self.network.n_sensor, dtype=np.bool_)
        stimulus = encoded.astype(np.float32) * np.float32(1.5)
        stimulated = any(key != "hour" for key in context) if active is None else active
        # Quiet periods run one low-duty background step instead of busy-spinning through
        # 125 silent 2 ms steps every 250 ms wall-clock interval.
        steps = max(1, round(duration_ms / self.network.dt_ms)) if stimulated else 1
        dt_s = duration_ms / 1000.0
        if self._tick_spike_counts.shape != self.network.population.spikes.shape:
            self._tick_spike_counts = np.zeros_like(self.network.population.spikes,
                                                    dtype=np.float32)
        self._tick_spike_counts.fill(0.0)
        for _ in range(steps):
            spikes = self.network.step(stimulus)
            self._tick_spike_counts += spikes
            dt_step = self.network.dt_ms / 1000.0
            h = slice(self.network.hidden_start, self.network.output_start)
            out = slice(self.network.output_start, self.network.output_start + self.network.hidden_to_output.n_post)
            self.learners["sensor_hidden"].mark(self.network.sensor_to_hidden,
                spikes[:self.network.n_sensor], spikes[h], dt_step)
            self.learners["recurrent"].mark(self.network.recurrent, spikes[h], spikes[h], dt_step)
            self.learners["hidden_output"].mark(self.network.hidden_to_output, spikes[h], spikes[out], dt_step)
            health_events = self.homeostasis.update(
                self.network.population, spikes, dt_step,
                (self.network.sensor_to_hidden, self.network.recurrent,
                 self.network.hidden_to_output))
            for event in health_events:
                self.action_log.record("homeostasis", event, 0.0, "system")
        self.last_rates = self.decoder.update(self._tick_spike_counts, dt_s)
        activity = float(self._tick_spike_counts.mean() / steps)
        hidden_counts = self._tick_spike_counts[
            self.network.hidden_start:self.network.output_start]
        peak_hidden_count = max(1.0, float(hidden_counts.max(initial=0.0)))
        self._last_hidden_activity = np.minimum(
            hidden_counts / np.float32(peak_hidden_count), 1.0).astype(np.float32, copy=True)
        category = context.get("window_category")
        if isinstance(category, str):
            self._recent_hidden_activity.pop(category, None)
            self._recent_hidden_activity[category] = self._last_hidden_activity
            if len(self._recent_hidden_activity) > 64:
                self._recent_hidden_activity.pop(next(iter(self._recent_hidden_activity)))
        if contacted:
            self.neuromodulators.add_mood_impulse(
                0.12, self._mood_slow_component_fraction)
            self.neuromodulators.stress = max(0.0, self.neuromodulators.stress - 0.03)
        budget_cap = self._non_deliberate_mood_budget_cap
        if self._last_rpe_is_deliberate:
            mood_budget = None
            mood_budget_now = 0.0
        else:
            mood_budget_now = time.monotonic()
            mood_budget = self._rate_budget_available(
                "mood", budget_cap, mood_budget_now)
        mood_used = self.neuromodulators.update(
            dt_s, activity,
            relax_fast_tau_s=self._mood_relax_fast_tau_s,
            relax_slow_tau_s=self._mood_relax_slow_tau_s,
            positive_mood_budget=mood_budget)
        if mood_budget is not None and mood_used > 0.0:
            self._record_rate_budget("mood", mood_used, mood_budget_now)
        self.affect_impulse *= float(np.exp(-dt_s / self._affect_impulse_tau_s))
        if self.curiosity_impulse > 1e-8:
            self.curiosity_impulse *= float(np.exp(
                -dt_s / self._curiosity_impulse_tau_s))
        else:
            self.curiosity_impulse = 0.0
        self.learning_rpe = self.neuromodulators.dopamine
        if abs(self.neuromodulators.dopamine) < 1e-6:
            self._last_rpe_is_deliberate = True
        self.drives.update(dt_s, activity, contacted=contacted)
        self.emotions.update(
            self.neuromodulators, activity, self.drives.social,
            dt_s=dt_s, contacted=contacted, affect_impulse=self.affect_impulse,
            affect_happiness_gain=self._affect_happiness_gain,
            curiosity_impulse=self.curiosity_impulse,
            curiosity_base=self._curiosity_base,
            curiosity_inactivity_gain=self._curiosity_inactivity_gain,
            curiosity_energy_gain=self._curiosity_energy_gain)
        snapshot = VisualState.from_engine(
            self, spikes, activity,
            bool(active) if active is not None else bool(context))
        try:
            self.visual_updates.get_nowait()
        except queue.Empty:
            pass
        self.visual_updates.put_nowait(snapshot)
        return self.last_rates

    def _rate_budget_available(self, key: str, cap_per_minute: float,
                               now: float) -> float:
        cap = max(0.0, float(cap_per_minute))
        history = self._rate_budgets.get(key)
        if history is None:
            return cap
        while history and now - history[0][0] >= 60.0:
            history.popleft()
        used = sum(amount for _timestamp, amount in history)
        return max(0.0, cap - used)

    def _record_rate_budget(self, key: str, amount: float, now: float) -> None:
        if amount <= 0.0:
            return
        history = self._rate_budgets.setdefault(key, deque())
        history.append((now, float(amount)))

    def _consume_rate_budget(self, key: str, requested: float, cap_per_minute: float,
                             now: float) -> float:
        if requested <= 0.0:
            return 0.0
        granted = min(float(requested),
                      self._rate_budget_available(key, cap_per_minute, now))
        self._record_rate_budget(key, granted, now)
        return granted

    def process_curiosity_observation(self, source: str, category: str,
                                      now: float | None = None) -> float:
        """Apply bounded, habituating novelty to curiosity only; never rewards or affect."""
        source = str(source)
        category = str(category)
        if source == "mouse" and category not in {
                "near_moving", "near_still", "far_moving", "far_still"}:
            return 0.0
        caps = self.curiosity_config.get("per_minute_cap", {})
        cap = float(caps.get(source, 0.0)) if isinstance(caps, dict) else 0.0
        base_gain = float(self.curiosity_config.get(
            f"impulse_gain_{source}", 0.0))
        if cap <= 0.0 or base_gain <= 0.0:
            return 0.0
        current = time.monotonic() if now is None else float(now)
        key = (source, category)
        previous = self._novelty_last_seen.get(key, current)
        recovery_tau = max(1.0, float(self.curiosity_config.get(
            "recovery_tau_s", 180.0)))
        load = self._novelty_load.get(key, 0.0) * float(
            np.exp(-max(0.0, current - previous) / recovery_tau))
        novelty = base_gain * max(0.0, 1.0 - load)
        applied = self._consume_rate_budget(
            f"curiosity:{source}", novelty, cap, current)
        step = min(1.0, max(0.0, float(self.curiosity_config.get(
            "habituation_step", 0.35))))
        self._novelty_load[key] = min(1.0, load + step * (1.0 - load))
        self._novelty_last_seen[key] = current
        impulse_max = max(0.0, float(self.curiosity_config.get("impulse_max", 0.05)))
        self.curiosity_impulse = min(impulse_max, self.curiosity_impulse + applied)
        return applied

    def reset_affect_to_neutral(self, *, save: bool = True) -> None:
        """Reset emotional state without touching neural weights or learned preferences."""
        self.neuromodulators.mood = 0.5
        self.neuromodulators.mood_fast_component = 0.0
        self.neuromodulators.mood_slow_component = 0.0
        self.neuromodulators.dopamine = 0.0
        self.neuromodulators.stress = 0.15
        self.affect_impulse = 0.0
        self.curiosity_impulse = 0.0
        self.learning_rpe = 0.0
        self._last_rpe_is_deliberate = True
        self.emotions.happiness = 0.5
        self.emotions.fear = 0.15
        self.emotions.curiosity = 0.5
        self.emotions.boredom = 0.2
        self.emotions.affection = 0.3
        self.emotions.trust = 0.5
        self.emotions.contact_comfort = 0.0
        self.emotions.recent_contact = 0.0
        if save:
            self.save()

    def reward(self, context: str, value: float, action: str = "", *,
               source: str | None = None) -> float:
        """Route one reward event to independent affect and learning channels.

        `affect_impulse` is immediate and not prediction-adjusted. Only the
        source/context-specific `learning_rpe` is allowed to modify synapses.
        `value` is an event strength in [0, 1].
        """
        if source is None:
            source = "feedback_positive" if value >= 0.0 else "feedback_negative"
        channel = self.reward_channels.get(source, {})
        strength = max(0.0, min(1.0, abs(float(value))))
        deliberate_sources = {
            "affection", "feedback_positive", "feedback_negative",
            "proposal_accepted", "proposal_rejected",
        }
        deliberate = source in deliberate_sources
        self._last_rpe_is_deliberate = deliberate
        affect = float(channel.get("affect_impulse", 0.0)) * strength
        if affect > 0.0:
            if not deliberate:
                cap = max(0.0, float(self.affect_config.get(
                    "non_deliberate_impulse_per_minute", 0.08)))
                affect = self._consume_rate_budget(
                    f"affect:{source}", affect, cap, time.monotonic())
            affect *= max(0.0, 1.0 - self.neuromodulators.mood)
        self.affect_impulse = max(-1.0, min(1.0, self.affect_impulse + affect))

        target_reward = float(channel.get("learning_reward", 0.0)) * strength
        prediction_key = f"{source}:{context}:{action}" if action else f"{source}:{context}"
        raw_rpe = self.neuromodulators.prediction_error(
            prediction_key, target_reward,
            rate=float(self.learning_config.get("prediction_rate", 0.05)))
        deadband = max(0.0, float(self.learning_config.get("rpe_deadband", 0.01)))
        self.learning_rpe = raw_rpe if abs(raw_rpe) > deadband else 0.0
        self.neuromodulators.dopamine = self.learning_rpe
        if context:
            self.network.activate_existing_output_context(
                self._context_projection_id(context))
        action_group = self.network.output_groups.get(f"tool:{action}") if action else None
        if action_group is not None:
            # Reward for a named tool must credit that output group specifically;
            # otherwise all output groups receive the same undirected update.
            output_indices = (action_group - self.network.output_start).astype(np.int32)
            self.learners["hidden_output"].apply_action_credit(
                self.network.hidden_to_output, self.learning_rpe, output_indices,
                self._recent_hidden_activity.get(context, self._last_hidden_activity),
                learning_rate=float(self.plasticity_config.get("action_credit_rate", 0.10)))
        else:
            for name, projection in (
                    ("sensor_hidden", self.network.sensor_to_hidden),
                    ("recurrent", self.network.recurrent),
                    ("hidden_output", self.network.hidden_to_output)):
                self.learners[name].apply_reward(projection, self.learning_rpe)

        self.memory.add(context, action, target_reward, str(asdict(self.emotions)))
        self.personality.update(target_reward)
        if action in {tool.name for tool in self.registry.all()} and target_reward != 0.0:
            self.selector.feedback(context, action, target_reward)
        return self.learning_rpe

    def decide_action(self, context: str = "default") -> ActionCandidate | None:
        candidates = []
        for tool in self.registry.all():
            ids = self.network.output_groups.get(f"tool:{tool.name}")
            score = float(self.last_rates.get(f"tool:{tool.name}", 0.0))
            if ids is not None and score >= 0.2:
                candidates.append(ActionCandidate(tool.name, score, tool.risk, context))
        initiative = float(self.last_rates.get("iniciativa", 0.0))
        return self.selector.choose(candidates, initiative)

    def execute_tool(self, name: str, params: dict[str, object] | None = None, *,
                     accepted: bool = False, explicit: bool = False,
                     context_category: str = "outro") -> dict[str, object]:
        tool = self.registry.get(name)
        if not self.permissions.authorize(tool, accepted=accepted, explicit=explicit):
            self.action_log.record(name, "blocked_or_waiting_for_confirmation", 0.0, context_category)
            return {"status": "confirmation_required"}
        if tool.run is None:
            raise RuntimeError(f"tool {name} has no run function")
        safe_params = dict(params or {})
        if name == "abrir_url":
            safe_params["explicit_user_action"] = explicit
        try:
            result = tool.run(safe_params)
        except Exception:
            self.action_log.record(name, "failure", -0.2, context_category)
            self.reward(context_category, 1.0, name, source="tool_failure")
            raise
        if tool.undo is not None:
            undo_params: dict[str, object] = dict(safe_params)
            undo_params["_result"] = result
            self._undo_stack.append((tool, undo_params))
        self.action_log.record(name, "success", 0.1, context_category)
        self.reward(context_category, 1.0, name, source="tool_success")
        return {"status": "success", "result": result}

    def _dispatch_tool(self, name: str, params: dict[str, object] | None = None, *,
                       accepted: bool = False, context_category: str = "outro") -> None:
        """Run potentially slow tools away from the simulation thread."""
        tool = self.registry.get(name)
        if not self.permissions.authorize(tool, accepted=accepted):
            self.action_log.record(name, "blocked_or_waiting_for_confirmation", 0.0,
                                   context_category)
            self.action_results.put({"operation": "tool", "status": "blocked",
                                     "tool": name})
            return
        if tool.run is None:
            raise RuntimeError(f"tool {name} has no run function")
        safe_params = dict(params or {})
        future = self._tool_executor.submit(tool.run, safe_params)
        future.add_done_callback(lambda finished: self._queue_tool_completion(
            finished, name, context_category, safe_params))

    def _queue_tool_completion(self, future: Future, name: str, context: str,
                               params: dict[str, object]) -> None:
        try:
            result = future.result()
        except BaseException as exc:
            self.events.put({"_tool_completion": {
                "name": name, "context": context, "params": params,
                "error": exc,
            }})
        else:
            self.events.put({"_tool_completion": {
                "name": name, "context": context, "params": params,
                "result": result,
            }})

    def _finish_tool(self, completion: dict[str, object]) -> None:
        name = str(completion.get("name", "unknown"))
        context = str(completion.get("context", "outro"))
        params = completion.get("params", {})
        safe_params = dict(params) if isinstance(params, dict) else {}
        error = completion.get("error")
        if isinstance(error, BaseException):
            self._log_exception(f"Ferramenta {name!r} falhou", error)
            self.action_log.record(name, "failure", -0.2, context)
            self.reward(context, 1.0, name, source="tool_failure")
            self.action_results.put({"operation": "tool", "status": "error",
                                     "tool": name, "error": str(error)})
            return
        tool = self.registry.get(name)
        result = completion.get("result", {})
        if tool.undo is not None:
            safe_params["_result"] = result
            self._undo_stack.append((tool, safe_params))
        self.action_log.record(name, "success", 0.1, context)
        self.reward(context, 1.0, name, source="tool_success")
        self.action_results.put({"operation": "tool", "status": "success",
                                 "tool": name, "result": result})

    def _expire_pending_proposals(self) -> None:
        now = time.monotonic()
        for name, expires_at in tuple(self._pending_tools.items()):
            if now >= expires_at:
                self._pending_tools.pop(name, None)
                self._proposal_cooldowns[name] = now + self._proposal_timeout_s
                self.logger.warning("Proposta %r expirou sem resposta", name)
                self.action_results.put({"operation": "proposal", "status": "timeout",
                                         "tool": name})

    def undo_last(self) -> dict[str, object]:
        if not self._undo_stack:
            return {"status": "nothing_to_undo"}
        tool, params = self._undo_stack.pop()
        if tool.undo is None:
            return {"status": "not_undoable"}
        result = tool.undo(params)
        self.action_log.record(tool.name, "undone", 0.0, "system")
        return {"status": "undone", "result": result}

    def reload_user_plugins(self) -> list[str]:
        """Load trusted plugins on explicit request and grow their output groups."""
        names = self.registry.load_user_plugins(self.data_dir / "user_tools")
        for name in names:
            self.network.add_tool_group(name)
        if names:
            self.decoder = RateDecoder(self.network.output_groups)
        return names

    def submit_tool_response(self, name: str, accepted: bool | None,
                             context_category: str = "outro") -> None:
        self.events.put({"_tool_request": name, "_accepted": accepted,
                         "_tool_context": context_category})

    def set_sensor_enabled(self, name: str, enabled: bool) -> None:
        self.sensor_manager.set_enabled(name, enabled)

    def _launch_simulation_thread(self) -> None:
        with self._thread_lock:
            if self._thread and self._thread.is_alive():
                return
            self.stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="synapse-pet-sim", daemon=True)
            self._thread.start()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._watchdog_stop.clear()
        if not self._sensors_started:
            try:
                self.sensor_manager.start_enabled()
                self._sensors_started = True
            except Exception as exc:
                self._log_exception("Falha ao iniciar sensores", exc)
        self._launch_simulation_thread()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, name="synapse-pet-watchdog", daemon=True)
        self._watchdog_thread.start()

    def _watchdog_loop(self) -> None:
        while not self._watchdog_stop.wait(0.5):
            if not self._started:
                return
            try:
                thread = self._thread
                if thread is None or not thread.is_alive():
                    if self.stop_event.is_set() and not self._restart_requested:
                        continue
                    self.logger.error("Thread de simulação morreu; tentando recuperar")
                    try:
                        if self._restore_last_snapshot():
                            self.logger.warning("Estado restaurado do último snapshot válido")
                    except BaseException as exc:
                        self._log_exception("Falha ao restaurar snapshot no watchdog", exc)
                    self._restart_requested = False
                    self._stall_reported = False
                    self.action_results.put({"operation": "runtime", "status": "restarted"})
                    self._launch_simulation_thread()
                    continue
                age = time.monotonic() - self._last_tick_at
                if age > self._watchdog_timeout_s and not self._stall_reported:
                    self._stall_reported = True
                    self._restart_requested = True
                    self.logger.error(
                        "Watchdog: tick parado há %.2f s; solicitando recuperação", age)
                    self.action_results.put({"operation": "runtime", "status": "stalled",
                                             "seconds_since_tick": age})
                    # Ask the worker to leave at the next safe loop boundary. The watchdog
                    # never starts a second writer while the old thread is still alive.
                    self.stop_event.set()
                elif age <= self._watchdog_timeout_s:
                    self._stall_reported = False
            except BaseException as exc:
                self._log_exception("Erro no watchdog da simulação", exc)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            work_started = time.thread_time()
            self._tick_in_progress = False
            try:
                self._run_iteration()
            except BaseException as exc:
                self._log_exception("Exceção no loop da simulação", exc)
                self.action_results.put({"operation": "runtime", "status": "error",
                                         "error": str(exc)})
                if self._tick_in_progress:
                    try:
                        if not self._restore_last_snapshot():
                            self.logger.warning(
                                "Sem snapshot anterior; continuando após falha do tick")
                        else:
                            self.logger.warning("Tick falhou; estado restaurado do snapshot")
                    except BaseException as restore_error:
                        self._log_exception("Falha na recuperação após erro de tick",
                                            restore_error)
            finally:
                self._tick_in_progress = False
                self.simulation_cpu_seconds += time.thread_time() - work_started

    def _run_iteration(self) -> None:
        try:
            context = self.events.get(timeout=0.25)
        except queue.Empty:
            context = {}
        if context.pop("_save", False):
            self._request_save()
            self._last_autosave = time.monotonic()
        if context.pop("_undo", False):
            try:
                self.action_results.put(self.undo_last())
            except Exception as exc:
                self._log_exception("Falha ao desfazer ação", exc)
                self.action_results.put({"operation": "undo", "status": "error",
                                         "error": str(exc)})
        completion = context.pop("_tool_completion", None)
        if isinstance(completion, dict):
            self._finish_tool(completion)
        contacted = bool(context.pop("_contacted", False))
        mouse_observation = context.pop("_mouse_observation", None)
        if isinstance(mouse_observation, str):
            self.process_curiosity_observation("mouse", mouse_observation)
        reward_source = context.pop("_reward_source", None)
        if isinstance(reward_source, str):
            self.reward("manual", 1.0, "carinho" if reward_source == "affection" else "",
                        source=reward_source)
        feedback = context.pop("_feedback", None)
        feedback_context = str(context.pop("_feedback_context", "manual"))
        if feedback is not None:
            amount = float(feedback)
            source = "feedback_positive" if amount >= 0.0 else "feedback_negative"
            self.reward(feedback_context, amount, source=source)
        tool_request = context.pop("_tool_request", None)
        accepted = context.pop("_accepted", None)
        tool_context = str(context.pop("_tool_context", "outro"))
        if isinstance(tool_request, str):
            expires_at = self._pending_tools.pop(tool_request, None)
            if expires_at is None or time.monotonic() > expires_at:
                self.action_results.put({"operation": "proposal", "status": "expired",
                                         "tool": tool_request})
            else:
                self._proposal_cooldowns[tool_request] = (
                    time.monotonic() + self._proposal_timeout_s)
            if expires_at is not None and time.monotonic() <= expires_at and accepted is True:
                self.reward(tool_context, 1.0, tool_request,
                            source="proposal_accepted")
                self._dispatch_tool(tool_request, accepted=True,
                                    context_category=tool_context)
            elif expires_at is not None and time.monotonic() <= expires_at and accepted is False:
                self.permissions.feedback(False)
                self.reward(tool_context, 1.0, tool_request,
                            source="proposal_rejected")
        self._expire_pending_proposals()
        sensor_context = self.sensor_manager.sample_context()
        active = bool(context) or self.sensor_manager.activity_detected or contacted
        context = {**sensor_context, **context}
        current_category = context.get("window_category")
        if isinstance(current_category, str):
            if (current_category != self._last_curiosity_context
                    and self.emotions.curiosity >= float(self.learning_config.get(
                        "curiosity_threshold", 0.72))):
                self.process_curiosity_observation("active_window", current_category)
            self._last_curiosity_context = current_category
        was_sleeping = self.sleep.sleeping
        self.sleep.update(0.25, active)
        now = time.monotonic()
        if active:
            self.scheduler.stimulus(now)
        self._last_regime = self.scheduler.regime(now, self.sleep.sleeping)
        tick_ms = float(self.config.get("network", {}).get(
            "tick_active_ms" if active else "tick_idle_ms", 50 if active else 250))
        self._tick_in_progress = True
        self.tick(context, tick_ms, active=active, contacted=contacted)
        self._tick_in_progress = False
        self._last_tick_at = time.monotonic()
        self._stall_reported = False
        category = str(context.get("window_category", "outro"))
        candidate = self.decide_action(category)
        if candidate is not None:
            if candidate.risk == "low":
                now = time.monotonic()
                if now - self._last_auto_action.get(candidate.name, 0.0) >= 300.0:
                    self._dispatch_tool(candidate.name, context_category=category)
                    self._last_auto_action[candidate.name] = now
            elif (candidate.risk == "medium"
                  and candidate.name not in self._pending_tools
                  and time.monotonic() >= self._proposal_cooldowns.get(candidate.name, 0.0)):
                self._pending_tools[candidate.name] = (
                    time.monotonic() + self._proposal_timeout_s)
                self.proposals.put(candidate)
        if self.sleep.sleeping and not was_sleeping:
            replayed = self.sleep.consolidate(self.network, self.memory,
                                              self.learners, self.neuromodulators)
            self.action_log.record("sleep", f"consolidated:{replayed}", 0.0, "system")
            self._request_save()
            self._last_autosave = time.monotonic()
        if time.monotonic() - self._last_autosave >= self._autosave_interval_s:
            self._request_save()
            self._last_autosave = time.monotonic()
        if self.sleep.sleeping:
            time.sleep(0.5)

    def _snapshot_state(self) -> dict[str, object]:
        preferences = [{"context": context, "action": action, "value": value}
                       for (context, action), value in self.selector.preferences.items()]
        return {"personality": self.personality.snapshot(),
                "neuromodulators": asdict(self.neuromodulators),
                "emotions": asdict(self.emotions), "drives": asdict(self.drives),
                "action_preferences": preferences,
                "refusal_streak": self.selector.refusal_streak,
                "min_silence_s": self.selector.min_silence_s,
                "encoder_rng": self.encoder.rng.bit_generator.state}

    def _save_completed(self, future: Future) -> None:
        try:
            future.result()
        except BaseException as exc:
            self._log_exception("Erro ao escrever snapshot", exc)
            self.action_results.put({"operation": "save", "status": "error",
                                     "error": str(exc)})
        else:
            self.action_results.put({"operation": "save", "status": "saved"})

    def _request_save(self) -> None:
        try:
            self.save(wait=False)
        except Exception as exc:
            self._log_exception("Falha ao preparar save", exc)
            self.action_results.put({"operation": "save", "status": "error",
                                     "error": str(exc)})

    def save(self, *, wait: bool = True) -> Future | None:
        """Capture on the caller and perform compression/disk I/O asynchronously in-loop."""
        if self._started and threading.current_thread() is not self._thread:
            self.submit_save()
            return None
        payload = self.store.capture(self.network, self._snapshot_state())
        if not wait or threading.current_thread() is self._thread:
            future = self._save_executor.submit(self.store.write_snapshot, payload)
            future.add_done_callback(self._save_completed)
            return future
        self.store.write_snapshot(payload)
        return None

    def stop(self) -> None:
        self._started = False
        self._watchdog_stop.set()
        self.stop_event.set()
        thread = self._thread
        if thread:
            thread.join(timeout=3.0)
        self.sensor_manager.stop()
        self._save_executor.shutdown(wait=True, cancel_futures=False)
        if thread and thread.is_alive():
            self.logger.error("Thread ainda viva durante shutdown; snapshot final adiado")
        else:
            try:
                self.save(wait=True)
            except Exception as exc:
                self._log_exception("Falha no snapshot final do shutdown", exc)
        self._tool_executor.shutdown(wait=False, cancel_futures=True)
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=1.0)
        self.logger.removeHandler(self._log_handler)
        self._log_handler.close()

    def submit_save(self) -> None:
        self.events.put({"_save": True})

    def submit_undo(self) -> None:
        self.events.put({"_undo": True})

    def submit_context(self, **context: object) -> None:
        self.events.put(context)

    def submit_mouse_attention(self, category: str) -> None:
        """Queue one coarse cursor category; screen coordinates never enter the engine."""
        if category in {"near_moving", "near_still", "far_moving", "far_still"}:
            self.events.put({"_mouse_observation": category})

    def submit_feedback(self, value: float, context: str = "manual") -> None:
        self.events.put({"_feedback": max(-1.0, min(1.0, value)),
                         "_feedback_context": context})

    def submit_affection(self) -> None:
        """Queue deliberate affection from the button or a qualified drag gesture."""
        self.events.put({"_reward_source": "affection", "_contacted": True})
