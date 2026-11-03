# Profiling da SNN

Relatório gerado por `snn_launch_comparison.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:322` — 0.4032 s cumulativos, 40 chamadas.
2. `mark` em `plasticity.py:24` — 0.2651 s cumulativos, 3000 chamadas.
3. `step` em `network.py:196` — 0.1043 s cumulativos, 1000 chamadas.
4. `currents` em `synapses.py:56` — 0.0568 s cumulativos, 3000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.0504 s cumulativos, 3000 chamadas.
