from __future__ import annotations

"""Render the markdown baseline report from the checked-in JSON evidence."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results"


def _f(value: float | None, places: int = 3) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _get(path: dict, *keys):
    for key in keys:
        path = path[key]
    return path


def render() -> str:
    baseline = json.loads((RESULTS / "baseline.json").read_text(encoding="utf-8"))
    components_doc = json.loads(
        (RESULTS / "baseline_components.json").read_text(encoding="utf-8"))
    components = components_doc["results"]
    environment = baseline["environment"]
    hardware = components_doc["platform"]
    historical_path = RESULTS / "snn_baseline_v03.json"
    historical = (json.loads(historical_path.read_text(encoding="utf-8"))
                  if historical_path.exists() else None)

    lines = [
        "# Baseline e profiling — Fase 1", "",
        f"**Data:** {baseline.get('timestamp_local', 'registrada no JSON')}", "",
        f"**Branch/commit:** `{environment['git']['branch']}` / `"
        f"{environment['git']['head'][:7]}`", "",
        "**Objetivo:** registrar custo antes da Fase 2; nenhuma otimização da SNN foi aplicada.", "",
        "## Ambiente", "",
        f"- SO: {environment['platform']}",
        f"- CPU: AMD Ryzen 7 5800H; {hardware['physical_cpus']} núcleos físicos / "
        f"{hardware['logical_cpus']} lógicos (reportado por Windows).",
        f"- Frequência reportada no início da coleta: "
        f"{_f(environment.get('cpu_frequency_mhz'), 0)} MHz; valor dinâmico, sem travar frequência.",
        f"- RAM física reportada: {hardware['ram_total_mib'] / 1024:.2f} GiB.",
        f"- Python `{environment['python'].split()[0]}`, NumPy `{environment['libraries']['numpy']}`, "
        f"SciPy `{environment['libraries']['scipy']}`, PySide6 Essentials "
        f"`{environment['libraries']['PySide6_Essentials']}`, psutil `{environment['libraries']['psutil']}`.",
        f"- Configuração: seed `{baseline['seed']}`, 600/1.000 solicitados, conectividade "
        f"{baseline['configuration']['network']['recurrent_connectivity']}, dt 2 ms, "
        f"50 ms/tick ativo (25 subpassos), 250 ms/tick repouso (um subpasso), ruído "
        f"{baseline['configuration']['network']['background_noise']}, ganho sináptico "
        f"{baseline['configuration']['network']['synaptic_gain']}, competição de ferramentas desligada.",
        "- Renderização, GPU/VRAM, consumo elétrico e desktop interativo não entram nesta medição do núcleo.",
        "", "## Tick ativo e memória", "",
        "| Rede solicitada | Total com ferramentas | CPU média/tick | Parede média ± DP | Parede P50 / P95 / P99 | RSS | Arrays NumPy | Conexões |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for requested, key in ((600, "tick_cost_600"), (1000, "tick_cost_1000")):
        tick = baseline[key]["active"]
        memory = baseline["memory"][str(requested)]
        structure = components["memory"]["runtime_engine"]["network"]
        if requested == 1000:
            # The legacy memory probe is measured in a fresh subprocess and
            # includes the tool groups; keep its actual neuron total here.
            total = memory["neurons_total_with_tools"]
        else:
            total = memory["neurons_total_with_tools"]
        lines.append(
            f"| {requested} | {total} | {_f(tick['mean_cpu_ms'])} ms | "
            f"{_f(tick['wall_ms']['mean'])} ± {_f(tick['wall_ms']['stddev'])} ms | "
            f"{_f(tick['wall_ms']['p50'])} / {_f(tick['wall_ms']['p95'])} / "
            f"{_f(tick['wall_ms']['p99'])} ms | {memory['rss_mib']:.2f} MiB | "
            f"{memory['numpy_array_bytes_unique'] / 1024:.1f} KiB | "
            f"{memory['connections']} |")

    lines.extend([
        "", "A CPU média/tick é o tempo de `thread_time_ns` total dividido pelo número de ticks. "
        "Os percentis de CPU individuais são preservados no JSON, mas Windows quantiza a medição; "
        "para percentis de latência use também as amostras de parede. O RSS é medido em processo "
        "limpo por tamanho; bytes de arrays incluem dados explícitos e buffers CSR únicos.",
        "", "### Comparação com o artefato histórico v0.3", "",
    ])
    if historical:
        lines.extend([
            "| Rede | CPU média histórica | CPU média atual | Diferença observada | Parede média histórica | Parede média atual |",
            "|---:|---:|---:|---:|---:|---:|",
        ])
        for requested, key in ((600, "tick_cost_600"), (1000, "tick_cost_1000")):
            old = historical[key]["active"]
            new = baseline[key]["active"]
            difference = 100.0 * (new["mean_cpu_ms"] - old["mean_cpu_ms"]) / old["mean_cpu_ms"]
            lines.append(
                f"| {requested} | {old['mean_cpu_ms']:.3f} ms | {new['mean_cpu_ms']:.3f} ms | "
                f"{difference:+.1f}% | {old['mean_wall_ms']:.3f} ms | "
                f"{new['mean_wall_ms']:.3f} ms |")
        lines.extend([
            "", "O baseline histórico v0.3 usou a mesma duração de 1.000 ticks e apresenta os "
            "mesmos contadores de conexões, mas não registra hardware, frequência, plano de energia "
            "nem versões completas das bibliotecas. O código SNN/runtime não tem alterações locais; "
            "a diferença atual é real nesta coleta, mas a causa não foi isolada. Não declarar ganho "
            "nem regressão de código sem uma comparação controlada no mesmo estado de energia/temperatura.",
        ])

    lines.extend([
        "", "## Firing rate e contagens de spikes", "",
        "O probe usa 80 ticks no regime e soma o tempo simulado. Taxas são disparos/neurônio/segundo; "
        "repouso/sono usam um único subpasso de 2 ms por tick, então sua janela simulada é curta.", "",
        "| Rede / regime | População sensor: spikes / Hz | Oculta: spikes / Hz | Saída: spikes / Hz |",
        "|---|---:|---:|---:|",
    ])
    for name, sample in baseline["spike_activity"].items():
        rates, spikes = sample["rates_hz"], sample["spikes"]
        lines.append(
            f"| {name} | {spikes['sensor']} / {rates['sensor']:.2f} | "
            f"{spikes['hidden']} / {rates['hidden']:.2f} | "
            f"{spikes['output']} / {rates['output']:.2f} |")

    lines.extend([
        "", "## Microbenchmarks por componente", "",
        "Cada linha usa wall samples individuais e CPU em lotes para reduzir a quantização do relógio "
        "de thread no Windows. A inicialização aquecida tem repetições; a primeira instância é uma "
        "medição única e inclui a primeira importação lazy de SciPy.", "",
        "| Componente | CPU média / P50 / P95 / P99 (ms) | Parede média ± DP (ms) | Parede P50 / P95 / P99 (ms) |",
        "|---|---:|---:|---:|",
    ])
    for name, item in components.items():
        if not isinstance(item, dict) or "wall_ms" not in item:
            continue
        cpu = item.get("cpu_ms") or {}
        wall = item["wall_ms"]
        cpu_text = " / ".join(_f(cpu.get(k)) for k in ("mean", "p50", "p95", "p99"))
        wall_quantiles = " / ".join(_f(wall[k]) for k in ("p50", "p95", "p99"))
        lines.append(
            f"| `{name}` | {cpu_text} | {_f(wall['mean'])} ± {_f(wall['stddev'])} | "
            f"{wall_quantiles} |")

    lines.extend([
        "", "### Alocações rastreadas", "",
        "`tracemalloc` roda em uma passada separada da medição de latência. Delta líquido é o número "
        "de blocos/bytes que continua vivo depois da amostra; alocações curtas que são liberadas dentro "
        "da função não aparecem nesse delta. Pico é bytes rastreados, não RSS.", "",
        "| Componente | Blocos líquidos/op | Bytes líquidos/op | Pico incremental/op |",
        "|---|---:|---:|---:|",
    ])
    for name, item in components.items():
        alloc = item.get("allocation_probe") if isinstance(item, dict) else None
        if not alloc:
            continue
        lines.append(
            f"| `{name}` | {_f(alloc['net_live_blocks_per_operation'], 2)} | "
            f"{_f(alloc['net_live_bytes_per_operation'], 1)} | "
            f"{_f(alloc['peak_traced_bytes_delta_per_operation'], 1)} |")

    lines.extend([
        "", "## Profiling", "",
        "Perfil ativo com `cProfile`: 120 ticks, 3.000 subpassos. Métricas cumulativas são aninhadas; "
        "a lista é para localizar caminhos, não para somar tempo.", "",
        "| # | Função | Chamadas | Cumulativo | Arquivo/linha |",
        "|---:|---|---:|---:|---|",
    ])
    for index, row in enumerate(baseline["top_profile_costs"], 1):
        lines.append(
            f"| {index} | `{row['function']}` | {row['calls']} | "
            f"{row['cumulative_seconds']:.4f} s | `{row['file']}:{row['line']}` |")
    lines.extend([
        "", "Arquivos `.prof`: `benchmarks/profile/baseline_active.prof` (componentes) e "
        "`benchmarks/profile/legacy_active.prof` (harness principal). Resumo: "
        "`benchmarks/profile/baseline_profile.md`.",
        "", "## Determinismo", "",
        f"- Seed `{baseline['determinism']['seed']}`, {baseline['determinism']['steps']} passos.",
        f"- `spike_sha256`: `{baseline['determinism']['spike_sha256']}`.",
        f"- `state_sha256`: `{baseline['determinism']['state_sha256']}`.",
        "- O teste de determinismo está incluído na suíte pytest; os hashes coincidem com o artefato histórico v0.3.",
        "", "## Repouso", "",
        f"CPU do processo no probe ocioso: {baseline['idle_process_cpu']['single_core_cpu_percent']:.3f}% "
        f"de um núcleo por {baseline['idle_process_cpu']['seconds']:.1f} s, com "
        "sensores desligados e intervalo ocioso padrão. Não é medição de energia elétrica.",
        "", "## Validação executada", "",
    ])
    validation_path = RESULTS / "validation_phase01.json"
    if validation_path.exists():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        lines.extend([
            f"- Comando: `{validation['command']}`.",
            f"- Resultado: **{validation['passed']} passed, {validation['failed']} failed, "
            f"{validation['collected']} coletados** em {validation['duration_s']:.2f} s.",
            f"- Falha: `{validation.get('failure_nodeid', 'nenhuma')}` — "
            f"{validation.get('failure_summary', '')}",
            f"- Ambiente headless: `{validation['qt_platform']}`; SO local Windows 11, "
            f"Python {validation['python_version']}. CI Python 3.12/Windows e Ubuntu não foi executada localmente.",
        ])
    else:
        lines.append("- Resultado pytest será adicionado em `validation_phase01.json`.")

    lines.extend([
        "", "## Reprodução", "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe benchmarks\\snn_baseline.py --ticks 1000 --profile-steps 120 --idle-seconds 10 --output benchmarks\\results\\baseline.json --profile-dir benchmarks\\profile",
        ".\\.venv\\Scripts\\python.exe benchmarks\\component_baseline.py --samples 100",
        ".\\.venv\\Scripts\\python.exe benchmarks\\render_baseline_report.py",
        "```", "",
        "Os JSONs guardam as amostras e o ambiente registrados. A faixa não representa um benchmark "
        "de renderização; GUI Windows, consumo da GPU e sensores físicos não foram validados.", "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    target = RESULTS / "baseline_report.md"
    target.write_text(render(), encoding="utf-8")
    print(target)
