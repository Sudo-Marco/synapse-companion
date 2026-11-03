# Profiling da SNN

Relatório gerado por `snn_mouse_affect_final_matched.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:189` — 1.0254 s cumulativos, 100 chamadas.
2. `mark` em `plasticity.py:24` — 0.6732 s cumulativos, 7500 chamadas.
3. `step` em `network.py:196` — 0.2662 s cumulativos, 2500 chamadas.
4. `currents` em `synapses.py:56` — 0.1447 s cumulativos, 7500 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1287 s cumulativos, 7500 chamadas.

Comparação com snn_context_projection_after.json (300 ticks): 600 neurônios = 9.01041666666667 → 9.0625 ms/tick; 1.000 = 18.90625 → 18.90625 ms/tick. A resolução do tempo de CPU nesta amostra é 15,625/300 = 0,052083 ms/tick; portanto, a diferença de 600 é uma unidade de quantização e a de 1.000 é zero. Os hashes de determinismo coincidem.
