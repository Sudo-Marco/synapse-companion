# Baseline e profiling — Fase 1

**Data:** registrada no JSON

**Branch/commit:** `feat/pet-sprite-sheet` / `d46c09f`

**Objetivo:** registrar custo antes da Fase 2; nenhuma otimização da SNN foi aplicada.

## Ambiente

- SO: Windows-11-10.0.26300-SP0
- CPU: AMD Ryzen 7 5800H; 8 núcleos físicos / 16 lógicos (reportado por Windows).
- Frequência reportada no início da coleta: 1802 MHz; valor dinâmico, sem travar frequência.
- RAM física reportada: 5.86 GiB.
- Python `3.14.10`, NumPy `2.5.4`, SciPy `1.18.1`, PySide6 Essentials `6.12.0`, psutil `7.2.2`.
- Configuração: seed `20261102`, 600/1.000 solicitados, conectividade 0.1, dt 2 ms, 50 ms/tick ativo (25 subpassos), 250 ms/tick repouso (um subpasso), ruído 0.015, ganho sináptico 1.7, competição de ferramentas desligada.
- Renderização, GPU/VRAM, consumo elétrico e desktop interativo não entram nesta medição do núcleo.

## Tick ativo e memória

| Rede solicitada | Total com ferramentas | CPU média/tick | Parede média ± DP | Parede P50 / P95 / P99 | RSS | Arrays NumPy | Conexões |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 600 | 712 | 12.672 ms | 12.907 ± 3.523 ms | 11.908 / 17.572 / 20.412 ms | 55.91 MiB | 337.4 KiB | 27561 |
| 1000 | 1112 | 25.031 ms | 25.457 ± 4.239 ms | 24.431 / 32.342 / 40.459 ms | 56.65 MiB | 857.3 KiB | 71208 |

A CPU média/tick é o tempo de `thread_time_ns` total dividido pelo número de ticks. Os percentis de CPU individuais são preservados no JSON, mas Windows quantiza a medição; para percentis de latência use também as amostras de parede. O RSS é medido em processo limpo por tamanho; bytes de arrays incluem dados explícitos e buffers CSR únicos.

### Comparação com o artefato histórico v0.3

| Rede | CPU média histórica | CPU média atual | Diferença observada | Parede média histórica | Parede média atual |
|---:|---:|---:|---:|---:|---:|
| 600 | 9.000 ms | 12.672 ms | +40.8% | 9.067 ms | 12.907 ms |
| 1000 | 18.719 ms | 25.031 ms | +33.7% | 18.816 ms | 25.457 ms |

O baseline histórico v0.3 usou a mesma duração de 1.000 ticks e apresenta os mesmos contadores de conexões, mas não registra hardware, frequência, plano de energia nem versões completas das bibliotecas. O código SNN/runtime não tem alterações locais; a diferença atual é real nesta coleta, mas a causa não foi isolada. Não declarar ganho nem regressão de código sem uma comparação controlada no mesmo estado de energia/temperatura.

## Firing rate e contagens de spikes

O probe usa 80 ticks no regime e soma o tempo simulado. Taxas são disparos/neurônio/segundo; repouso/sono usam um único subpasso de 2 ms por tick, então sua janela simulada é curta.

| Rede / regime | População sensor: spikes / Hz | Oculta: spikes / Hz | Saída: spikes / Hz |
|---|---:|---:|---:|
| active | 3473 / 9.04 | 7991 / 5.20 | 4448 / 4.79 |
| rest | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 |
| sleep | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 |
| 1000_active | 5087 / 7.95 | 14076 / 5.50 | 7312 / 5.86 |

## Microbenchmarks por componente

Cada linha usa wall samples individuais e CPU em lotes para reduzir a quantização do relógio de thread no Windows. A inicialização aquecida tem repetições; a primeira instância é uma medição única e inclui a primeira importação lazy de SciPy.

| Componente | CPU média / P50 / P95 / P99 (ms) | Parede média ± DP (ms) | Parede P50 / P95 / P99 (ms) |
|---|---:|---:|---:|
| `network_initialization_600_warm` | 3.906 / 3.348 / 4.520 / 5.368 | 3.630 ± 0.227 | 3.583 / 4.107 / 4.211 |
| `lif_update_600_runtime_population` | 0.038 / 0.043 / 0.043 / 0.043 | 0.046 ± 0.026 | 0.035 / 0.072 / 0.163 |
| `sparse_propagation_all_three_projections` | 0.050 / 0.050 / 0.051 / 0.064 | 0.054 ± 0.015 | 0.044 / 0.083 / 0.087 |
| `stdp_mark_all_three_projections` | 0.423 / 0.477 / 0.477 / 0.477 | 0.384 ± 0.047 | 0.367 / 0.479 / 0.565 |
| `reward_application_all_three_projections` | 0.166 / 0.146 / 0.195 / 0.195 | 0.157 ± 0.021 | 0.148 / 0.194 / 0.240 |
| `homeostasis_update_250ms` | 0.011 / 0.011 / 0.015 / 0.015 | 0.012 ± 0.032 | 0.004 / 0.014 / 0.159 |
| `decoder_update` | 0.081 / 0.078 / 0.104 / 0.104 | 0.083 ± 0.032 | 0.074 / 0.122 / 0.159 |
| `full_tick_active_50ms_25_substeps` | 11.875 / 12.500 / 12.500 / 12.500 | 12.407 ± 1.558 | 12.101 / 16.050 / 18.277 |
| `full_tick_rest_250ms_one_substep` | 0.704 / 0.660 / 0.880 / 0.880 | 0.705 ± 0.101 | 0.669 / 0.994 / 1.036 |
| `stimulus_encoding_rates_and_poisson_spikes` | 0.093 / 0.080 / 0.133 / 0.133 | 0.085 ± 0.025 | 0.074 / 0.145 / 0.179 |
| `network_growth_600_to_800_excludes_template_copy` | 3.977 / 4.261 / 5.682 / 5.682 | 4.955 ± 0.921 | 4.989 / 6.151 / 6.769 |
| `snapshot_save_capture_compress_atomic_write` | 14.062 / 15.625 / 15.625 / 15.625 | 13.643 ± 0.460 | 13.624 / 14.384 / 14.514 |
| `snapshot_load_checksum_rebuild` | 13.281 / 15.625 / 15.625 / 15.625 | 12.825 ± 1.640 | 12.325 / 15.057 / 15.849 |
| `network_initialization_600_first_instance` | 265.625 / 265.625 / 265.625 / 265.625 | 322.760 ± 0.000 | 322.760 / 322.760 / 322.760 |

### Alocações rastreadas

`tracemalloc` roda em uma passada separada da medição de latência. Delta líquido é o número de blocos/bytes que continua vivo depois da amostra; alocações curtas que são liberadas dentro da função não aparecem nesse delta. Pico é bytes rastreados, não RSS.

| Componente | Blocos líquidos/op | Bytes líquidos/op | Pico incremental/op |
|---|---:|---:|---:|
| `network_initialization_600_warm` | 17.75 | 1264.0 | 347466.0 |
| `lif_update_600_runtime_population` | 0.65 | 56.8 | 309.4 |
| `sparse_propagation_all_three_projections` | 0.85 | 69.4 | 319.0 |
| `stdp_mark_all_three_projections` | 0.70 | 51.2 | 9502.4 |
| `reward_application_all_three_projections` | 4.20 | 455.6 | 9739.6 |
| `homeostasis_update_250ms` | 1.40 | 113.2 | 9398.8 |
| `decoder_update` | 2.05 | 120.4 | 366.2 |
| `full_tick_active_50ms_25_substeps` | 19.60 | 1280.8 | 10862.5 |
| `full_tick_rest_250ms_one_substep` | 8.15 | 495.1 | 10046.0 |
| `stimulus_encoding_rates_and_poisson_spikes` | 5.30 | 566.8 | 664.4 |
| `network_growth_600_to_800_excludes_template_copy` | 34.50 | 2364.0 | 514077.2 |
| `snapshot_save_capture_compress_atomic_write` | 63.75 | 2941.0 | 272433.2 |

## Profiling

Perfil ativo com `cProfile`: 120 ticks, 3.000 subpassos. Métricas cumulativas são aninhadas; a lista é para localizar caminhos, não para somar tempo.

| # | Função | Chamadas | Cumulativo | Arquivo/linha |
|---:|---|---:|---:|---|
| 1 | `tick` | 120 | 1.6109 s | `engine.py:371` |
| 2 | `mark` | 9000 | 1.0550 s | `plasticity.py:24` |
| 3 | `step` | 3000 | 0.4233 s | `network.py:236` |
| 4 | `currents` | 9000 | 0.2285 s | `synapses.py:56` |
| 5 | `__matmul__` | 9000 | 0.2024 s | `_base.py:1006` |

Arquivos `.prof`: `benchmarks/profile/baseline_active.prof` (componentes) e `benchmarks/profile/legacy_active.prof` (harness principal). Resumo: `benchmarks/profile/baseline_profile.md`.

## Determinismo

- Seed `20261102`, 4096 passos.
- `spike_sha256`: `45c47b8e06e2f7dfff2a61832f9d07d5cc4197c8ee35c82df65e3260bbcc92b7`.
- `state_sha256`: `d34fec09870ee66aa118d91bfc1293c44e9b2fddb14ab6990eb742d330978279`.
- O teste de determinismo está incluído na suíte pytest; os hashes coincidem com o artefato histórico v0.3.

## Repouso

CPU do processo no probe ocioso: 0.312% de um núcleo por 10.0 s, com sensores desligados e intervalo ocioso padrão. Não é medição de energia elétrica.

## Validação executada

- Comando: `.\.venv\Scripts\python.exe -m pytest -q`.
- Resultado: **141 passed, 1 failed, 142 coletados** em 24.49 s.
- Falha: `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back` — A expectativa de mover o pet para baixo no salto triste foi bloqueada pelo limite inferior da tela virtual offscreen: y ficou em 628, igual à geometria inicial. Reprodução consistente; nenhum código ou asserção foi alterado.
- Ambiente headless: `offscreen`; SO local Windows 11, Python 3.14.10. CI Python 3.12/Windows e Ubuntu não foi executada localmente.

## Reprodução

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --ticks 1000 --profile-steps 120 --idle-seconds 10 --output benchmarks\results\baseline.json --profile-dir benchmarks\profile
.\.venv\Scripts\python.exe benchmarks\component_baseline.py --samples 100
.\.venv\Scripts\python.exe benchmarks\render_baseline_report.py
```

Os JSONs guardam as amostras e o ambiente registrados. A faixa não representa um benchmark de renderização; GUI Windows, consumo da GPU e sensores físicos não foram validados.
