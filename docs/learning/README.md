# Fase 2: avaliação de aprendizado

Execute a partir da raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.sim.learning_eval --output docs\learning
```

O simulador usa 600 neurônios, seed `20261102`, três ferramentas fictícias (`eval_a` a `eval_c`) e três categorias (`X`, `Y`, `Z`). As escolhas de treino têm 20% de exploração; a avaliação é gulosa e não atualiza o estado. Nenhuma ferramenta real é executada.

| Cenário | Treino / avaliação | Critério |
| --- | --- | --- |
| a | 150 / 100 episódios em X | >85% |
| b | 120 antes + 120 após a reversão; 100 de avaliação | Readaptação ≤60 episódios e >85% final |
| c | 100 episódios por contexto, intercalados; 40 por contexto de avaliação | >80% em X, Y e Z |
| d | 500 episódios, 10% de feedback invertido; 100 de avaliação | >70% |
| e | 120 em X, 1000 em Y, 100 de avaliação em X | >70% retido |

O acerto principal usa a pontuação combinada: taxa neural por ferramenta normalizada e preferência aprendida por contexto/ferramenta. O CSV inclui ablações que mostram separadamente a previsão neural e a preferência. `action_gate_eligible` verifica o limiar neural da ferramenta; `production_action_available` também verifica o limiar de iniciativa usado pelo seletor real.

O resultado atual passa os cinco critérios da política combinada. A ablação neural-only ainda não passa em todos: em particular, a reversão e X em cenário c dependem das preferências contextuais. Os pesos se alteram, mas a SNN isolada ainda não é um classificador confiável para todas essas situações. Consulte `results.json` e `scenario_[a-e].csv` para os valores completos por episódio. Os PNGs mostram acerto combinado, acerto neural-only, probabilidade do alvo, RPE e variação relativa de pesos.
