# Profiling da SNN

Relatório gerado por `phase3_backend_numpy.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:379` — 1.7510 s cumulativos, 120 chamadas.
2. `update_stdp` em `numpy_backend.py:38` — 1.1548 s cumulativos, 9000 chamadas.
3. `mark` em `plasticity.py:28` — 1.1488 s cumulativos, 9000 chamadas.
4. `step` em `network.py:249` — 0.4538 s cumulativos, 3000 chamadas.
5. `propagate` em `numpy_backend.py:33` — 0.2453 s cumulativos, 9000 chamadas.
