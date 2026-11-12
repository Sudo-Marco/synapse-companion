# Otimização Python — plano e resultados da Fase 2

**Status:** Fase 2 implementada e medida; Fase 3 não iniciada.

**Regra:** preservar a topologia LIF, a ordem temporal, os canais de recompensa e o hash de determinismo existente, salvo aprovação explícita para mudança semântica.

## Medição de partida

O baseline atual está em [baseline.json](../../benchmarks/results/baseline.json), os testes de componentes em [baseline_components.json](../../benchmarks/results/baseline_components.json), o relatório legível em [baseline_report.md](../../benchmarks/results/baseline_report.md) e os perfis cProfile em `benchmarks/profile/`.

O perfil ativo de 120 ticks aponta maior tempo acumulado em:

| Função | Chamadas | Tempo cumulativo no perfil | Interpretação |
|---|---:|---:|---|
| `PetEngine.tick` | 120 | 1,611 s | engloba o restante do pipeline |
| `RewardSTDP.mark` | 9.000 | 1,055 s | maior rotina interna observada; três projeções por subpasso |
| `SpikingNetwork.step` | 3.000 | 0,423 s | 25 subpassos/tick ativo |
| `SparseProjection.currents` | 9.000 | 0,228 s | três multiplicações CSR por subpasso |
| `csr_matrix.__matmul__` | 9.000 | 0,202 s | multiplicação CSR executada dentro de `currents` |

Os tempos cumulativos se sobrepõem; não somar linhas aninhadas. A aquisição de tick completo em execução normal é mais representativa que cProfile, que adiciona overhead.

## Ordem proposta para experimentos

Cada experimento deve ser isolado, medido antes/depois com o mesmo Python, SciPy/NumPy, rede, seed, ticks e política de energia. Guardar JSON novo em `benchmarks/results/`, não substituir a baseline original. Rodar determinismo e testes funcionais antes de aceitar uma alteração.

1. **STDP (`plasticity.py`)** — medir separadamente os `astype(float32)`, indexações por aresta e buffers de elegibilidade. Hipótese: reduzir vetores temporários, reaproveitando buffers sem modificar as equações nem a ordem dos updates. Verificar diretamente spikes, traces, elegibilidade, pesos e Dale, além do hash de referência.
2. **Buffers do tick (`network.py`)** — avaliar buffer `current` reutilizável em vez de alocar `np.zeros` em cada subpasso. Requer ownership exclusivo da thread do engine e proteção contra retenção do array por consumidores; não retornar buffer mutável para UI/snapshot.
3. **Propagação CSR (`synapses.py`)** — medir separadamente `matrix @ spikes` e a soma/escala do resultado. Comparar o caminho SciPy com alternativa de acumulação esparsa apenas em microbenchmark; manter fallback e validar equivalência numérica.
4. **Crédito de ação** — medir `np.isin(projection.post, post_indices)` em relação ao número de saídas/arestas. Uma máscara por grupo pode ser cacheada apenas se a topologia permanecer estável e a invalidação ocorrer em `add_tool_group`, crescimento, rebuild e load.
5. **Construção/growth** — avaliar geração esparsa sem matriz aleatória densa transitória. Este item afeta startup e crescimento, não o tick normal; não alterar antes de equivalência determinística das arestas/weights ser decidida.
6. **Decodificação/encoder** — investigar pequenos custos do loop de grupos e criação repetida de `linspace` nos grupos numéricos. Só prosseguir se o perfil mostrar peso relevante após os gargalos principais.

## Critérios de aceite propostos

- Para 600 e 1.000 neurônios, comparar média, desvio, P50/P95/P99 de CPU e parede; meta inicial é não piorar acima de 3% e medir redução real.
- Repetir tick ativo e repouso, RAM/RSS, bytes de arrays, spikes por população e taxa de disparo.
- Confirmar hash `spike_sha256` e `state_sha256` atuais (ou documentar mudança aprovada), testes de core, persistência, contexto, aprendizado e runtime.
- Distinguir regressão de variação por hardware/energia. O v0.3 histórico não registrou hardware/frequência e, nesta execução, o tick atual ficou acima dos tempos históricos; não comparar resultados sem o mesmo ambiente.
- Não migrar para Cython, C/C++ nem alterar a topologia LIF durante os experimentos iniciais.

## Hipóteses não confirmadas

- O perfil sugere que STDP será o maior ganho potencial, mas a parcela inclui conversões e indexing de NumPy; nenhuma operação deve ser removida sem profiling granular e teste de equivalência.
- O CSR parece ocupar menos tempo que STDP neste perfil. Trocar a representação poderia aumentar custo ou alterar a ordem de soma; não é uma otimização presumida.
- As taxas elevadas observadas em uma execução histórica curta de 1.000 neurônios não são prova de instabilidade; elas variam entre runs e precisam de um teste de estabilidade longo antes de orientar mudança de algoritmo.

## Resultado da Fase 2

Foram implementados e testados: buffer `current` reutilizado em `SpikingNetwork.step`, conversões de spike com buffers pré-alocados em `RewardSTDP.mark`, e lookup booleano para crédito de ação com fallback de `np.isin` em entradas atípicas. Equações, topologia, formato de snapshot e dependências não mudaram.

O benchmark completo de 1.000 ticks comparou 600 e 1.000 neurônios. A média de parede ficou +0,75% e +2,42%, respectivamente; as médias de CPU ficaram 0,00% e +1,76%. P50/P95/P99 e a ressalva sobre frequência dinâmica do processador estão em [PHASE2_OPTIMIZATION_REPORT.md](PHASE2_OPTIMIZATION_REPORT.md). Os hashes de spikes e estado permaneceram idênticos à referência. No microbenchmark isolado, o lookup de crédito reduziu parede em cerca de 24%; a comparação de STDP não mostrou ganho significativo. A alternativa `bincount` foi medida e rejeitada por custo e diferença numérica.

A suíte local coletou 148 testes: 147 passaram e um teste visual offscreen falhou por geometria no limite inferior da tela. O relatório detalhado, comandos e arquivos de resultado estão em [PHASE2_OPTIMIZATION_REPORT.md](PHASE2_OPTIMIZATION_REPORT.md). Isso encerra a otimização Python; backend híbrido/Cython permanece para a próxima fase autorizada.
