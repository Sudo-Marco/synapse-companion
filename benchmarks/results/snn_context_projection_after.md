# Profiling da SNN

Relatório gerado por `snn_context_projection_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:160` — 1.0254 s cumulativos, 100 chamadas.
2. `mark` em `plasticity.py:24` — 0.6754 s cumulativos, 7500 chamadas.
3. `step` em `network.py:196` — 0.2674 s cumulativos, 2500 chamadas.
4. `currents` em `synapses.py:56` — 0.1463 s cumulativos, 7500 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1301 s cumulativos, 7500 chamadas.
