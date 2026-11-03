# Profiling da SNN

Relatório gerado por `snn_runtime_resilience_after.json`.

Cinco maiores custos por tempo cumulativo durante ticks ativos:

1. `tick` em `engine.py:301` — 1.0224 s cumulativos, 100 chamadas.
2. `mark` em `plasticity.py:24` — 0.6699 s cumulativos, 7500 chamadas.
3. `step` em `network.py:196` — 0.2662 s cumulativos, 2500 chamadas.
4. `currents` em `synapses.py:56` — 0.1454 s cumulativos, 7500 chamadas.
5. `__matmul__` em `_base.py:1006` — 0.1293 s cumulativos, 7500 chamadas.

Comparação com snn_context_projection_after.json (300 ticks): 600 neurônios = 9.01041666666667 → 9.11458333333333 ms/tick; 1.000 = 18.90625 → 18.90625 ms/tick. Os hashes de determinismo coincidem. A resolução observada do contador de CPU nesta amostra é 15,625/300 = 0,052083 ms/tick; a diferença bruta em 600 é de duas unidades do contador. O perfil cumulativo de 	ick variou -0.030093 ms/tick.
