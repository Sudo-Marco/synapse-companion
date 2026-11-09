# Profiling da SNN

Relatório gerado por `baseline.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 1.6109 s cumulativos, 120 chamadas.
2. `mark` em `plasticity.py:24` — 1.0550 s cumulativos, 9000 chamadas.
3. `step` em `network.py:236` — 0.4233 s cumulativos, 3000 chamadas.
4. `currents` em `synapses.py:56` — 0.2285 s cumulativos, 9000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.2024 s cumulativos, 9000 chamadas.
