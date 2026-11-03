# Profiling da SNN

Relatório gerado por `snn_mouse_affect_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:172` — 1.0332 s cumulativos, 100 chamadas.
2. `mark` em `plasticity.py:24` — 0.6727 s cumulativos, 7500 chamadas.
3. `step` em `network.py:196` — 0.2721 s cumulativos, 2500 chamadas.
4. `currents` em `synapses.py:56` — 0.1481 s cumulativos, 7500 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1318 s cumulativos, 7500 chamadas.
