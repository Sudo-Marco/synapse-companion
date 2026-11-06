# Profiling da SNN

Relatório gerado por `snn_baseline_v03.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 0.4182 s cumulativos, 40 chamadas.
2. `mark` em `plasticity.py:24` — 0.2743 s cumulativos, 3000 chamadas.
3. `step` em `network.py:236` — 0.1079 s cumulativos, 1000 chamadas.
4. `currents` em `synapses.py:56` — 0.0588 s cumulativos, 3000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.0523 s cumulativos, 3000 chamadas.
