# Profiling da SNN

Relatório gerado por `snn_context_projection_before.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:150` — 1.0297 s cumulativos, 100 chamadas.
2. `mark` em `plasticity.py:24` — 0.6744 s cumulativos, 7500 chamadas.
3. `step` em `network.py:64` — 0.2708 s cumulativos, 2500 chamadas.
4. `currents` em `synapses.py:48` — 0.1465 s cumulativos, 7500 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1296 s cumulativos, 7500 chamadas.
