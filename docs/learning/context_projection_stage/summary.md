# Ajustes aprovados: taxas de crédito e projeção contextual

Avaliação offline, seed 20261102, 600 neurônios. Nenhum teste foi iniciado no app real; nenhuma tarefa da Fase 3 foi iniciada.

## Grade de taxas

Os resultados abaixo medem o cenário b. “SNN estrita” significa que o seletor por preferências foi desligado durante treino e avaliação. As outras colunas mantêm a política combinada normal.

| Crédito de ação | Taxa de previsão | Política combinada: readaptação / acerto | SNN estrita: readaptação / acerto |
| ---: | ---: | ---: | ---: |
| 0,08 | 0,05 | 44 / 100% | 49 / 99% |
| 0,08 | 0,10 | 44 / 100% | sem janela ≥85% / 62% |
| 0,08 | 0,20 | 44 / 100% | sem janela ≥85% / 26% |
| **0,10** | **0,05** | **44 / 100%** | **49 / 100% — escolhida** |
| 0,10 | 0,10 | 44 / 100% | 49 / 76% |
| 0,10 | 0,20 | 44 / 100% | sem janela ≥85% / 28% |
| 0,15 | 0,05 | 44 / 100% | 49 / 100% |
| 0,15 | 0,10 | 43 / 100% | 49 / 99% |
| 0,15 | 0,20 | 44 / 100% | 63 / 82% |

A escolha foi action_credit_rate 0.10 e prediction_rate 0.05. A SNN estrita empatou no maior acerto de b com a taxa de crédito 0,15, mantendo readaptação em 49 episódios; 0,10 foi escolhida por atingir o mesmo acerto com menor crédito e menor variação dos pesos. A política combinada readaptou em 44 episódios. O CSV completo está em [rate_grid.csv](rate_grid.csv).

## Projeções de saída por contexto

A topologia esparsa CSR é compartilhada. Cada contexto ganha um vetor de pesos separado apenas quando aparece; a primeira projeção começa dos pesos-base. Uma assinatura sensorial semelhante a uma já conhecida pode copiar seus pesos iniciais se o cosseno superar context_projections.similarity_threshold. O limite é max_contexts: 8; ao excedê-lo, a projeção menos usada é removida (LRU). O snapshot grava os vetores, assinaturas e ordem de uso, usando IDs hash em vez dos nomes crus dos contextos.

## Cenários finais

A ablação SNN-only remove a preferência contextual na decisão de avaliação, mas usa pesos aprendidos durante o protocolo de treino misto. A grade acima mede separadamente o treino estritamente SNN-only de b. Percentuais de contribuição são a decomposição média, em valor absoluto, dos dois termos do score do vencedor combinado: taxa SNN normalizada e preferência contextual. São uma medida de composição do score, não uma atribuição causal.

| Cenário | Política combinada | SNN-only na avaliação | Fração do score: SNN / seletor |
| --- | ---: | ---: | ---: |
| a | 100% | 100% | 43% / 57% |
| b | 100%; readaptou em 44 episódios | 100% (treino estrito: 100%, 49 episódios) | 21% / 79% |
| c, contexto X | 100% | 100% | 24% / 76% |
| c, contexto Y | 100% | 97,5% | 40% / 60% |
| c, contexto Z | 100% | 77,5% | 32% / 68% |
| d, 10% de feedback ruidoso | 100% | 100% | 31% / 69% |
| e, retenção após interferência | 100% | 67% | 29% / 71% |

A acurácia combinada de a, c, d e e permaneceu em 100% (sem regressão percentual); b terminou em 100% e readaptou em 44 episódios. A meta isolada de c passou nos três contextos: X 100%, Y 97,5%, Z 77,5%. No cenário e, a política combinada reteve 100%, embora a saída neural sozinha tenha 67%; o seletor ainda tem uma contribuição relevante nesse cenário.

## Custo e integridade

O benchmark executou PetEngine.tick com o mesmo comando e 300 ticks por modo; o contexto editor foi ativado e reutilizado durante a medição.

| Rede | Antes | Depois | Delta observado | Limite |
| ---: | ---: | ---: | ---: | ---: |
| 600 neurônios | 9,0104 ms/tick | 9,0104 ms/tick | +0,0000 ms | +0,20 ms |
| 1.000 neurônios | 18,9583 ms/tick | 18,9063 ms/tick | −0,0521 ms | +0,20 ms |

O delta negativo em 1.000 neurônios é variação de medição, não uma alegação de aceleração. A alteração ficou dentro do orçamento em ambos os tamanhos. O determinismo manteve os mesmos hashes antes/depois (spikes 45c47b8e…cc92b7; estado d34fec09…978279, 4.096 passos). Os 38 testes passaram, incluindo snapshots com projeções, round-trip ZIP, migração de snapshot v1 e descarte LRU. O relatório comparativo dos benchmarks está em benchmarks/results/snn_context_projection_after.json.

Artefatos da avaliação e curvas: [results.json](results.json), scenario_a.png–scenario_e.png e os respectivos CSVs nesta pasta.
