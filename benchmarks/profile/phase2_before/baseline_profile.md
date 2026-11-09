# Profiling da SNN

Relatório gerado por `phase2_before.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 1.7366 s cumulativos, 120 chamadas.
2. `mark` em `plasticity.py:24` — 1.1405 s cumulativos, 9000 chamadas.
3. `step` em `network.py:236` — 0.4526 s cumulativos, 3000 chamadas.
4. `currents` em `synapses.py:56` — 0.2430 s cumulativos, 9000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.2154 s cumulativos, 9000 chamadas.
