# Profiling da SNN

Relatório gerado por `phase2_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 1.6603 s cumulativos, 120 chamadas.
2. `mark` em `plasticity.py:28` — 1.0839 s cumulativos, 9000 chamadas.
3. `step` em `network.py:239` — 0.4383 s cumulativos, 3000 chamadas.
4. `currents` em `synapses.py:56` — 0.2348 s cumulativos, 9000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.2078 s cumulativos, 9000 chamadas.
