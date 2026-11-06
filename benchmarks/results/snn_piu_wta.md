# Profiling da SNN

Relatório gerado por `snn_piu_wta.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:371` — 0.4147 s cumulativos, 40 chamadas.
2. `mark` em `plasticity.py:24` — 0.2670 s cumulativos, 3000 chamadas.
3. `step` em `network.py:236` — 0.1136 s cumulativos, 1000 chamadas.
4. `currents` em `synapses.py:56` — 0.0586 s cumulativos, 3000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.0518 s cumulativos, 3000 chamadas.
