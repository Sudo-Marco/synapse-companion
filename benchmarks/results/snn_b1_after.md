# Profiling da SNN

Relatório gerado por `snn_b1_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:327` — 0.8413 s cumulativos, 80 chamadas.
2. `mark` em `plasticity.py:24` — 0.5483 s cumulativos, 6000 chamadas.
3. `step` em `network.py:196` — 0.2196 s cumulativos, 2000 chamadas.
4. `currents` em `synapses.py:56` — 0.1203 s cumulativos, 6000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1068 s cumulativos, 6000 chamadas.
