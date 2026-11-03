# Profiling da SNN

Relatório gerado por `snn_baseline_phase1.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:139` — 0.8069 s cumulativos, 80 chamadas.
2. `mark` em `plasticity.py:24` — 0.5362 s cumulativos, 6000 chamadas.
3. `step` em `network.py:63` — 0.2037 s cumulativos, 2000 chamadas.
4. `currents` em `synapses.py:48` — 0.1167 s cumulativos, 6000 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1040 s cumulativos, 6000 chamadas.
