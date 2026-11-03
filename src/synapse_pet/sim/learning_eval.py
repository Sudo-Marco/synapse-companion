from __future__ import annotations

import argparse
import csv
import gc
import json
import math
from pathlib import Path
import random
import tempfile
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..runtime.engine import PetEngine
from ..runtime.config import load_config
from ..tools.manifest import ToolManifest


TOOLS = ("eval_a", "eval_b", "eval_c")
CONTEXTS = ("X", "Y", "Z")
TARGETS = {"X": "eval_a", "Y": "eval_b", "Z": "eval_c"}
CONTEXT_INPUTS = {
    "X": {"input_rate": 0.18, "window_category": "X",
          "activity": 0.22, "hour": 0.20},
    "Y": {"input_rate": 0.50, "window_category": "Y",
          "activity": 0.50, "hour": 0.50},
    "Z": {"input_rate": 0.82, "window_category": "Z",
          "activity": 0.78, "hour": 0.80},
}
TEMPERATURE = 0.08
EXPLORATION = 0.20
MOVING_WINDOW = 20


def softmax_probabilities(logits: dict[str, float], temperature: float = TEMPERATURE
                          ) -> dict[str, float]:
    """Softmax the selector's actual score: neural rate plus learned preference."""
    if not logits:
        return {}
    temperature = max(1e-5, float(temperature))
    names = tuple(logits)
    values = np.asarray([float(logits[name]) for name in names], dtype=np.float64)
    values = np.exp((values - values.max()) / temperature)
    values /= max(float(values.sum()), 1e-12)
    return {name: float(value) for name, value in zip(names, values)}


class LearningSimulation:
    """Offline user simulator around the production engine's reward and selector."""

    def __init__(self, seed: int, neurons: int) -> None:
        self.seed = int(seed)
        self.rng = np.random.default_rng(seed)
        self._temporary = tempfile.TemporaryDirectory(prefix="synapse_learning_eval_")
        self.engine = PetEngine(seed=seed, neurons=neurons,
                                data_dir=Path(self._temporary.name))
        for name in TOOLS:
            self.engine.register_tool(ToolManifest(
                name, "Offline simulated action", "low", ("learning_eval",),
                run=lambda _params: {"ok": True},
            ))

        self.network = self.engine.network
        self._original_step = self.network.step
        self._spike_counts = np.zeros(3, dtype=np.int64)
        self.network.step = self._counted_step
        self.simulated_seconds_per_episode = 0.0
        self.start_weights = self._weights_copy()
        self.start_weight_norm = self._weights_norm(self.start_weights)
        self.episode_number = 0
        self.rows: list[dict[str, Any]] = []

    def _counted_step(self, current=None):
        spikes = self._original_step(current)
        hidden = slice(self.network.hidden_start, self.network.output_start)
        output = slice(self.network.output_start,
                       self.network.output_start + self.network.hidden_to_output.n_post)
        self._spike_counts += (
            int(spikes[:self.network.n_sensor].sum()),
            int(spikes[hidden].sum()),
            int(spikes[output].sum()),
        )
        self.simulated_seconds_per_episode += self.network.dt_ms / 1000.0
        return spikes

    def _weights_copy(self) -> tuple[np.ndarray, ...]:
        return tuple(projection.weights.copy() for projection in (
            self.network.sensor_to_hidden, self.network.recurrent,
            self.network.hidden_to_output))

    @staticmethod
    def _weights_norm(weights: tuple[np.ndarray, ...]) -> float:
        return math.sqrt(sum(float(np.dot(item.astype(np.float64),
                                         item.astype(np.float64)))
                             for item in weights))

    def _weight_delta_ratio(self) -> float:
        current = (self.network.sensor_to_hidden.weights,
                   self.network.recurrent.weights,
                   self.network.hidden_to_output.weights)
        delta_squared = sum(float(np.square(now.astype(np.float64)
                                            - before.astype(np.float64)).sum())
                            for now, before in zip(current, self.start_weights))
        return math.sqrt(delta_squared) / max(self.start_weight_norm, 1e-12)

    def _rates(self) -> dict[str, float]:
        seconds = max(self.simulated_seconds_per_episode, 1e-12)
        sizes = (self.network.n_sensor, self.network.n_hidden,
                 self.network.hidden_to_output.n_post)
        names = ("sensor", "hidden", "output")
        return {name: float(count / (seconds * size))
                for name, count, size in zip(names, self._spike_counts, sizes)}

    def _policy(self, context: str) -> tuple[dict[str, float], dict[str, float]]:
        logits = {
            tool: min(1.0, max(0.0, float(
                self.engine.last_rates.get(f"tool:{tool}", 0.0))
                / max(1e-6, self.engine.selector.neural_score_scale_hz)))
            + float(self.engine.selector.preferences.get((context, tool), 0.0))
            for tool in TOOLS
        }
        return logits, softmax_probabilities(logits)

    def episode(self, scenario: str, context: str, target: str, *,
                learn: bool, exploration: float = 0.0,
                feedback_noise: float = 0.0,
                phase: str = "train") -> dict[str, Any]:
        self._spike_counts.fill(0)
        self.simulated_seconds_per_episode = 0.0
        self.engine.tick(CONTEXT_INPUTS[context], duration_ms=50.0, active=True)
        neural_logits = {
            tool: float(self.engine.last_rates.get(f"tool:{tool}", 0.0))
            for tool in TOOLS
        }
        preference_logits = {
            tool: float(self.engine.selector.preferences.get((context, tool), 0.0))
            for tool in TOOLS
        }
        logits, probabilities = self._policy(context)
        greedy = max(logits, key=logits.get)
        neural_greedy = max(neural_logits, key=neural_logits.get)
        preference_greedy = max(preference_logits, key=preference_logits.get)
        if learn and self.rng.random() < exploration:
            action = str(self.rng.choice(TOOLS))
        else:
            action = str(self.rng.choice(
                TOOLS, p=np.asarray([probabilities[name] for name in TOOLS])))

        true_success = action == target
        observed_success = true_success
        if learn and feedback_noise > 0.0 and self.rng.random() < feedback_noise:
            observed_success = not observed_success
        rpe = 0.0
        if learn:
            source = "tool_success" if observed_success else "tool_failure"
            rpe = self.engine.reward(context, 1.0, action, source=source)

        self.episode_number += 1
        rates = self._rates()
        tool_gate_eligible = any(
            self.engine.last_rates.get(f"tool:{tool}", 0.0)
            >= self.engine.selector.threshold for tool in TOOLS)
        initiative_rate = float(self.engine.last_rates.get("iniciativa", 0.0))
        row: dict[str, Any] = {
            "scenario": scenario,
            "episode": self.episode_number,
            "phase": phase,
            "context": context,
            "target_tool": target,
            "chosen_tool": action,
            "greedy_tool": greedy,
            "neural_greedy_tool": neural_greedy,
            "preference_greedy_tool": preference_greedy,
            "true_success": int(true_success),
            "observed_success": int(observed_success),
            "learned": int(learn),
            "feedback_noise": feedback_noise,
            "learning_rpe": float(rpe),
            "weight_delta_ratio": self._weight_delta_ratio(),
            "firing_hz_sensor": rates["sensor"],
            "firing_hz_hidden": rates["hidden"],
            "firing_hz_output": rates["output"],
            "action_gate_eligible": int(tool_gate_eligible),
            "initiative_rate_hz": initiative_rate,
            "production_action_available": int(tool_gate_eligible and initiative_rate >= 0.5),
        }
        for tool in TOOLS:
            row[f"prob_{tool}"] = probabilities[tool]
            row[f"neural_rate_{tool}"] = neural_logits[tool]
            row[f"preference_{tool}"] = preference_logits[tool]
        self.rows.append(row)
        return row

    def close(self) -> None:
        self.network.step = self._original_step
        del self.engine
        gc.collect()
        self._temporary.cleanup()


def _evaluate(sim: LearningSimulation, scenario: str, context: str, target: str,
              repetitions: int, phase: str = "eval") -> list[dict[str, Any]]:
    return [sim.episode(scenario, context, target, learn=False,
                        phase=phase) for _ in range(repetitions)]


def _accuracy(rows: list[dict[str, Any]], prediction_field: str = "greedy_tool") -> float:
    if not rows:
        return 0.0
    return float(np.mean([int(row[prediction_field] == row["target_tool"])
                          for row in rows]))


def _target_probability(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return float(np.mean([row[f"prob_{row['target_tool']}"] for row in rows]))


def _final_probabilities(sim: LearningSimulation, contexts: tuple[str, ...]
                         ) -> dict[str, dict[str, float]]:
    result = {}
    for context in contexts:
        sim._spike_counts.fill(0)
        sim.simulated_seconds_per_episode = 0.0
        sim.engine.tick(CONTEXT_INPUTS[context], duration_ms=50.0, active=True)
        _logits, probabilities = sim._policy(context)
        result[context] = probabilities
    return result


def _scenario_a(seed: int, neurons: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sim = LearningSimulation(seed, neurons)
    try:
        rows = [sim.episode("a", "X", "eval_a", learn=True,
                            exploration=EXPLORATION) for _ in range(150)]
        evaluation = _evaluate(sim, "a", "X", "eval_a", 100)
        rows.extend(evaluation)
        probabilities = _final_probabilities(sim, ("X",))
        result = {"accuracy": _accuracy(evaluation),
                  "neural_only_accuracy": _accuracy(evaluation, "neural_greedy_tool"),
                  "preference_only_accuracy": _accuracy(evaluation, "preference_greedy_tool"),
                  "target_probability": _target_probability(evaluation),
                  "weight_delta_ratio": sim._weight_delta_ratio(),
                  "mean_hidden_firing_hz": float(np.mean(
                      [row["firing_hz_hidden"] for row in rows])),
                  "action_gate_eligible_eval_fraction": float(np.mean(
                      [row["action_gate_eligible"] for row in evaluation])),
                  "production_action_available_eval_fraction": float(np.mean(
                      [row["production_action_available"] for row in evaluation])),
                  "probabilities": probabilities}
        result["passed"] = result["accuracy"] > 0.85
        return result, rows
    finally:
        sim.close()


def _scenario_b(seed: int, neurons: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sim = LearningSimulation(seed, neurons)
    try:
        rows: list[dict[str, Any]] = []
        rows.extend(sim.episode("b", "X", "eval_a", learn=True,
                                exploration=EXPLORATION, phase="before_reversal")
                    for _ in range(120))
        reversal_rows = [sim.episode("b", "X", "eval_b", learn=True,
                                     exploration=EXPLORATION, phase="after_reversal")
                         for _ in range(120)]
        rows.extend(reversal_rows)
        adapted_at = None
        for end in range(MOVING_WINDOW, len(reversal_rows) + 1):
            window = reversal_rows[end - MOVING_WINDOW:end]
            if _accuracy(window) >= 0.85:
                adapted_at = end
                break
        evaluation = _evaluate(sim, "b", "X", "eval_b", 100,
                               phase="eval_after_reversal")
        rows.extend(evaluation)
        probabilities = _final_probabilities(sim, ("X",))
        result = {"post_reversal_accuracy": _accuracy(evaluation),
                  "neural_only_accuracy": _accuracy(evaluation, "neural_greedy_tool"),
                  "preference_only_accuracy": _accuracy(evaluation, "preference_greedy_tool"),
                  "post_reversal_target_probability": _target_probability(evaluation),
                  "readaptation_episodes": adapted_at,
                  "readaptation_limit": 60,
                  "weight_delta_ratio": sim._weight_delta_ratio(),
                  "mean_hidden_firing_hz": float(np.mean(
                      [row["firing_hz_hidden"] for row in rows])),
                  "action_gate_eligible_eval_fraction": float(np.mean(
                      [row["action_gate_eligible"] for row in evaluation])),
                  "production_action_available_eval_fraction": float(np.mean(
                      [row["production_action_available"] for row in evaluation])),
                  "probabilities": probabilities}
        result["passed"] = (adapted_at is not None and adapted_at <= 60
                            and result["post_reversal_accuracy"] > 0.85)
        return result, rows
    finally:
        sim.close()


def _scenario_c(seed: int, neurons: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sim = LearningSimulation(seed, neurons)
    try:
        rng = random.Random(seed + 3)
        training = [(context, TARGETS[context])
                    for _ in range(100) for context in CONTEXTS]
        rng.shuffle(training)
        rows = [sim.episode("c", context, target, learn=True,
                            exploration=EXPLORATION) for context, target in training]
        evaluations: dict[str, list[dict[str, Any]]] = {}
        for context in CONTEXTS:
            evaluations[context] = _evaluate(sim, "c", context, TARGETS[context], 40)
            rows.extend(evaluations[context])
        accuracies = {context: _accuracy(items)
                      for context, items in evaluations.items()}
        probabilities = _final_probabilities(sim, CONTEXTS)
        result = {"accuracy_by_context": accuracies,
                  "neural_only_accuracy_by_context": {
                      context: _accuracy(items, "neural_greedy_tool")
                      for context, items in evaluations.items()},
                  "preference_only_accuracy_by_context": {
                      context: _accuracy(items, "preference_greedy_tool")
                      for context, items in evaluations.items()},
                  "target_probability_by_context": {
                      context: _target_probability(items)
                      for context, items in evaluations.items()},
                  "weight_delta_ratio": sim._weight_delta_ratio(),
                  "mean_hidden_firing_hz": float(np.mean(
                      [row["firing_hz_hidden"] for row in rows])),
                  "action_gate_eligible_eval_fraction": {
                      context: float(np.mean([row["action_gate_eligible"] for row in items]))
                      for context, items in evaluations.items()},
                  "production_action_available_eval_fraction": {
                      context: float(np.mean([row["production_action_available"] for row in items]))
                      for context, items in evaluations.items()},
                  "probabilities": probabilities}
        result["passed"] = all(value > 0.80 for value in accuracies.values())
        return result, rows
    finally:
        sim.close()


def _scenario_d(seed: int, neurons: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sim = LearningSimulation(seed, neurons)
    try:
        rows = [sim.episode("d", "X", "eval_c", learn=True,
                            exploration=EXPLORATION, feedback_noise=0.10)
                for _ in range(500)]
        evaluation = _evaluate(sim, "d", "X", "eval_c", 100)
        rows.extend(evaluation)
        probabilities = _final_probabilities(sim, ("X",))
        result = {"accuracy": _accuracy(evaluation),
                  "neural_only_accuracy": _accuracy(evaluation, "neural_greedy_tool"),
                  "preference_only_accuracy": _accuracy(evaluation, "preference_greedy_tool"),
                  "target_probability": _target_probability(evaluation),
                  "feedback_noise": 0.10,
                  "weight_delta_ratio": sim._weight_delta_ratio(),
                  "mean_hidden_firing_hz": float(np.mean(
                      [row["firing_hz_hidden"] for row in rows])),
                  "action_gate_eligible_eval_fraction": float(np.mean(
                      [row["action_gate_eligible"] for row in evaluation])),
                  "production_action_available_eval_fraction": float(np.mean(
                      [row["production_action_available"] for row in evaluation])),
                  "probabilities": probabilities}
        result["passed"] = result["accuracy"] > 0.70
        return result, rows
    finally:
        sim.close()


def _scenario_e(seed: int, neurons: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sim = LearningSimulation(seed, neurons)
    try:
        rows = [sim.episode("e", "X", "eval_a", learn=True,
                            exploration=EXPLORATION, phase="learn_old_context")
                for _ in range(120)]
        rows.extend(sim.episode("e", "Y", "eval_b", learn=True,
                                exploration=EXPLORATION, phase="interference_context")
                    for _ in range(1000))
        evaluation = _evaluate(sim, "e", "X", "eval_a", 100,
                               phase="eval_retained_context")
        rows.extend(evaluation)
        probabilities = _final_probabilities(sim, ("X", "Y"))
        result = {"retained_context_accuracy": _accuracy(evaluation),
                  "neural_only_accuracy": _accuracy(evaluation, "neural_greedy_tool"),
                  "preference_only_accuracy": _accuracy(evaluation, "preference_greedy_tool"),
                  "retained_context_target_probability": _target_probability(evaluation),
                  "interference_episodes": 1000,
                  "weight_delta_ratio": sim._weight_delta_ratio(),
                  "mean_hidden_firing_hz": float(np.mean(
                      [row["firing_hz_hidden"] for row in rows])),
                  "action_gate_eligible_eval_fraction": float(np.mean(
                      [row["action_gate_eligible"] for row in evaluation])),
                  "production_action_available_eval_fraction": float(np.mean(
                      [row["production_action_available"] for row in evaluation])),
                  "probabilities": probabilities}
        result["passed"] = result["retained_context_accuracy"] > 0.70
        return result, rows
    finally:
        sim.close()


SCENARIOS = {
    "a": _scenario_a,
    "b": _scenario_b,
    "c": _scenario_c,
    "d": _scenario_d,
    "e": _scenario_e,
}


def _draw_curve(path: Path, scenario: str, rows: list[dict[str, Any]]) -> None:
    width, height = 1000, 620
    image = Image.new("RGB", (width, height), (5, 10, 16))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.text((32, 22), f"SYNAPSE PET · LEARNING SCENARIO {scenario.upper()}",
              fill=(62, 216, 227), font=font)
    draw.text((32, 45), "Combined / neural-only accuracy, target probability, |RPE| and weight drift",
              fill=(132, 157, 164), font=font)
    left, right, top, bottom = 70, width - 35, 95, 410
    draw.rectangle((left, top, right, bottom), outline=(30, 56, 68), width=1)
    for tick in range(6):
        y = bottom - round((bottom - top) * tick / 5)
        draw.line((left, y, right, y), fill=(20, 39, 49), width=1)
        draw.text((30, y - 5), f"{tick * 20}%", fill=(100, 125, 132), font=font)

    learned = [row for row in rows if row["learned"]]
    if not learned:
        draw.text((left + 12, top + 12), "No training episodes", fill=(220, 220, 210), font=font)
    else:
        xdenom = max(1, len(learned) - 1)
        curves: list[tuple[str, tuple[int, int, int], list[float]]] = []
        accuracy = []
        neural_accuracy = []
        for index, row in enumerate(learned):
            low = max(0, index - MOVING_WINDOW + 1)
            window = learned[low:index + 1]
            accuracy.append(float(np.mean([
                int(item["greedy_tool"] == item["target_tool"]) for item in window])))
            neural_accuracy.append(float(np.mean([
                int(item["neural_greedy_tool"] == item["target_tool"])
                for item in window])))
        target_probability = [float(row[f"prob_{row['target_tool']}"])
                              for row in learned]
        rpe = [min(1.0, abs(float(row["learning_rpe"]))) for row in learned]
        max_weight_delta = max((float(row["weight_delta_ratio"]) for row in learned),
                               default=0.0)
        weight = [float(row["weight_delta_ratio"]) / max(max_weight_delta, 1e-12)
                  for row in learned]
        curves.extend((
            ("Greedy accuracy (20 ep.)", (243, 190, 106), accuracy),
            ("Neural-only accuracy (20 ep.)", (241, 113, 128), neural_accuracy),
            ("Target action probability", (62, 216, 227), target_probability),
            ("Absolute RPE", (232, 133, 101), rpe),
            ("Weight change (scaled to run max)", (185, 139, 236), weight),
        ))
        for _label, color, values in curves:
            points = []
            for index, value in enumerate(values):
                x = left + round((right - left) * index / xdenom)
                y = bottom - round((bottom - top) * max(0.0, min(1.0, value)))
                points.append((x, y))
            if len(points) == 1:
                draw.point(points[0], fill=color)
            else:
                draw.line(points, fill=color, width=2)

    legend_y = 440
    legend_items = (
        ("Greedy accuracy (20 ep.)", (243, 190, 106)),
        ("Neural-only accuracy (20 ep.)", (241, 113, 128)),
        ("Target action probability", (62, 216, 227)),
        ("Absolute RPE", (232, 133, 101)),
        ("Weight change (scaled to run max)", (185, 139, 236)),
    )
    for index, (label, color) in enumerate(legend_items):
        x = 80 + (index % 2) * 430
        y = legend_y + (index // 2) * 26
        draw.line((x, y + 6, x + 28, y + 6), fill=color, width=3)
        draw.text((x + 38, y), label, fill=(196, 213, 214), font=font)

    draw.text((32, 535), f"Training episodes: {len(learned)}  ·  Evaluation episodes: "
              f"{sum(1 for row in rows if not row['learned'])}",
              fill=(132, 157, 164), font=font)
    draw.text((32, 558), "RPE is thresholded by the configured deadband; weight change is "
              "relative to the initial L2 norm; its curve is scaled to this run's maximum.",
              fill=(100, 125, 132), font=font)
    image.save(path)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["scenario", "episode", "phase", "context", "target_tool",
              "chosen_tool", "greedy_tool", "neural_greedy_tool",
              "preference_greedy_tool", "true_success", "observed_success",
              "learned", "feedback_noise", "learning_rpe", "weight_delta_ratio",
              "firing_hz_sensor", "firing_hz_hidden", "firing_hz_output",
              "action_gate_eligible", "initiative_rate_hz", "production_action_available",
              *(f"prob_{tool}" for tool in TOOLS),
              *(f"neural_rate_{tool}" for tool in TOOLS),
              *(f"preference_{tool}" for tool in TOOLS)]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_evaluation(output: Path, seed: int = 20261102,
                   neurons: int = 600) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    config = load_config()
    network_config = config.get("network", {})
    learning_config = config.get("learning", {})
    plasticity_config = config.get("plasticity", {})
    context_projection_config = config.get("context_projections", {})
    results: dict[str, Any] = {
        "seed": seed,
        "neurons_requested": neurons,
        "synaptic_gain": float(network_config.get("synaptic_gain", 1.0)),
        "action_preference_rate": float(learning_config.get("action_preference_rate", 0.30)),
        "neural_score_scale_hz": float(learning_config.get("neural_score_scale_hz", 15.0)),
        "action_credit_rate": float(plasticity_config.get("action_credit_rate", 0.10)),
        "prediction_rate": float(learning_config.get("prediction_rate", 0.05)),
        "context_projections": {
            "max_contexts": int(context_projection_config.get("max_contexts", 8)),
            "similarity_threshold": float(context_projection_config.get(
                "similarity_threshold", 0.85)),
            "weight_topology": "shared sparse CSR; context-specific lazy weight vectors",
        },
        "synaptic_gain": 1.7,
        "action_preference_rate": 0.30,
        "exploration_rate": EXPLORATION,
        "softmax_temperature": TEMPERATURE,
        "thresholds": {"a": ">85%", "b": "readapt <=60 episodes and >85% final",
                       "c": ">80% in each context", "d": ">70% at 10% feedback noise",
                       "e": ">70% retained after 1000 episodes in another context"},
        "scenarios": {},
    }
    for letter, runner in SCENARIOS.items():
        result, rows = runner(seed + ord(letter), neurons)
        results["scenarios"][letter] = result
        _write_csv(output / f"scenario_{letter}.csv", rows)
        _draw_curve(output / f"scenario_{letter}.png", letter, rows)
        print(f"{letter}) passed={result['passed']} "
              f"result={json.dumps(result, ensure_ascii=False, sort_keys=True)}")
    results["all_passed"] = all(item["passed"]
                                for item in results["scenarios"].values())
    results["readme_notes"] = (
        "Reported scenario accuracy is greedy combined-policy accuracy on held-out episodes. "
        "The combined score is the normalized decoded tool firing rate plus the learned context/tool "
        "preference. Neural-only and preference-only ablations are reported separately; "
        "exploration is only in this offline simulator. action_gate_eligible checks the "
        "tool-rate threshold; production_action_available additionally requires the actual "
        "initiative threshold. No tools are executed by this evaluation.")
    (output / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline contextual reward-learning evaluation")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[3]
                        / "docs" / "learning")
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--neurons", type=int, default=600)
    args = parser.parse_args()
    results = run_evaluation(args.output, seed=args.seed, neurons=args.neurons)
    print(f"Results: {args.output / 'results.json'}")
    print(f"All scenarios passed: {results['all_passed']}")


if __name__ == "__main__":
    main()
