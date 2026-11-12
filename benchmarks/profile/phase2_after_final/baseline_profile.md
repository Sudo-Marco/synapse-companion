# Profiling da SNN

Relatório gerado por `phase2_after_final.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 1.7471 s cumulativos, 120 chamadas.
2. `mark` em `plasticity.py:28` — 1.1549 s cumulativos, 9000 chamadas.
3. `step` em `network.py:239` — 0.4506 s cumulativos, 3000 chamadas.
4. `currents` em `synapses.py:56` — 0.2444 s cumulativos, 9000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.2171 s cumulativos, 9000 chamadas.
