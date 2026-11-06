# Profiling da SNN

Relatório gerado por `snn_piu_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 0.4086 s cumulativos, 40 chamadas.
2. `mark` em `plasticity.py:24` — 0.2669 s cumulativos, 3000 chamadas.
3. `step` em `network.py:236` — 0.1078 s cumulativos, 1000 chamadas.
4. `currents` em `synapses.py:56` — 0.0580 s cumulativos, 3000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.0516 s cumulativos, 3000 chamadas.
