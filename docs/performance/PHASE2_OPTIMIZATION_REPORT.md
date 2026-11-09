# Relatório da Fase 2 — otimização Python

**Status:** concluída, com uma falha conhecida na suíte visual headless.

**Data:** 8 de novembro de 2026.

**Escopo:** reduzir alocações e custo Python no caminho de tick, sem alterar dinâmica LIF, topologia, equações de aprendizado, persistência, dependências ou UI. A Fase 3 não foi iniciada.

## Resumo

Foram mantidas três mudanças localizadas: buffer de corrente reutilizado em `SpikingNetwork.step`; dois buffers `float32` de conversão reutilizados por `RewardSTDP.mark`; lookup booleano para crédito de ação, mantendo `np.isin` como fallback de compatibilidade. Os hashes de spikes e estado para 4.096 passos permaneceram idênticos à referência. A média de parede do tick ativo aumentou 0,75% em 600 neurônios e 2,42% em 1.000, dentro do limite de 3%; a medição de CPU subiu 0,00% e 1,76%.

O crédito de ação teve ganho no microbenchmark. A alteração STDP reduziu conversões/alocações, mas seu ganho de tempo foi pequeno e não se traduziu em ganho mensurável do tick ativo. A troca de CSR por `numpy.bincount` foi descartada: ficou mais lenta e deixou de ser bit a bit equivalente.

## Alterações implementadas

| Área | Mudança | Compatibilidade |
|---|---|---|
| Rede | `current` é um array de trabalho reaproveitado e zerado com `fill`; é redimensionado se grupos dinâmicos alterarem o tamanho da população. | O vetor de spikes retornado continua sendo uma cópia; não há alias mutável entregue ao consumidor. |
| STDP | `mark()` copia spikes para buffers `float32` pré-alocados e mantém a sequência numérica da fórmula. | Teste de equivalência bit a bit para traces e elegibilidade, com projeções e sequências de atividade variadas. |
| Crédito de ação | Lookup booleano denso para índices inteiros dentro do intervalo válido. Casos inválidos/incomuns continuam usando `np.isin`. | Máscaras e pesos após atualizações repetidas são exatamente iguais à implementação anterior. |
| Propagação | Avaliada alternativa com `numpy.bincount`; mantida a implementação SciPy CSR. | `bincount` divergiu até `5,96e-8` em `float32` e não preservou os hashes; foi 2,4–6,7 vezes mais lenta nos casos medidos. |

Não houve mudança em neurônios LIF, conectividade, número de sinapses, regras de aprendizado, formato de snapshot, pacote/dependência, canais de recompensa ou renderização.

## Tick completo: baseline e versão otimizada

Executados 1.000 ticks ativos por configuração antes e depois, na mesma máquina e com seed 20261102. “Solicitados” é a configuração de neurônios; “totais” inclui grupos de ferramentas dinâmicos.

| Rede | CPU média antes → depois | Parede média antes → depois | Parede P50 antes → depois | P95 antes → depois | P99 antes → depois | Mudança parede média |
|---|---:|---:|---:|---:|---:|---:|
| 600 solicitados / 712 totais | 12,672 → 12,672 ms | 12,825 → 12,921 ms | 12,089 → 12,049 ms | 16,938 → 17,144 ms | 20,172 → 20,165 ms | **+0,75%** |
| 1.000 solicitados / 1.112 totais | 24,797 → 25,234 ms | 25,209 → 25,820 ms | 24,351 → 24,768 ms | 31,393 → 31,333 ms | 38,013 → 37,282 ms | **+2,42%** |

CPU e parede são relógios distintos. No Windows, `thread_time` é quantizado em passos de aproximadamente 15,625 ms no benchmark; por isso os percentis de CPU por tick são pouco informativos. Os dados de parede têm resolução adequada para comparar as distribuições. O benchmark final também registrou tick de repouso em 600 neurônios: média de parede 0,734 → 0,713 ms (−2,81%).

Bytes de arrays NumPy ficaram constantes: 345.536 B em 712 neurônios e 877.892 B em 1.112. RSS caiu de 56,348 para 56,246 MiB e de 56,828 para 56,703 MiB, respectivamente; variações pequenas de RSS não devem ser tratadas como ganho garantido. O pico de memória rastreada em um tick ativo do benchmark de componentes caiu de 10.820,6 para 10.556,5 B (−2,44%).

### Limite da comparação

O processador reportou frequência de 3.201 MHz durante o baseline e 1.802 MHz durante a medição final. Isso pode influenciar os tempos médios, portanto os resultados não demonstram aceleração global. Para reduzir esse viés, o benchmark A/B em processo único alternou a ordem das variantes, com 40 amostras de 20 ticks por modo, e verificou igualdade exata do estado final. Nesse A/B, parede ativa foi +1,53% (600) e −0,64% (1.000). O P99 de 600 foi +3,4% nessa amostra pequena; o benchmark completo de 1.000 ticks mostra P99 −0,04% (600) e −1,92% (1.000). As medições são compatíveis com custo ativo dentro da meta de 3%, sem evidência de um ganho geral de velocidade.

## Experimentos dos componentes

| Experimento | Resultado | Decisão |
|---|---|---|
| STDP, 40 amostras × 400 chamadas, três projeções | Parede média 0,38280 → 0,38079 ms (−0,52%); equivalência exata. Pico rastreado 9.502 → 9.343 B (−1,7%). | Manter scratch buffers pela redução de temporários sem mudança matemática; não anunciar ganho de tick. |
| Crédito de ação, 30 amostras × 100 atualizações | `np.isin` 0,15204 ms; implementação final 0,11593 ms (−23,8%). Todos os métodos avaliados produziram máscara e pesos exatamente iguais. | Adotar lookup com guardas e fallback. O método de runs ordenados foi mais rápido no microbenchmark, mas depende mais da ordenação interna da CSR e não foi escolhido. |
| CSR vs `bincount`, 30 amostras × 100 propagações | CSR SciPy ficou mais rápido em todas as projeções/rates. A alternativa diferiu em ponto flutuante até `5,96e-8` nos casos de maior atividade. | Rejeitar a substituição para preservar desempenho e determinismo. |
| Buffer `current` | Reduz alocação repetida de `zeros`; o benchmark completo permaneceu dentro do limite, mas sem ganho de média de tick ativo demonstrável. | Manter para reduzir alocações no caminho de integração; buffer permanece interno e reutilizável. |

Uma tentativa exploratória de multiplicar diretamente arrays booleanos na STDP foi mais lenta (~7,5% em parede) e foi removida antes da validação final.

## Determinismo e testes

Os dois hashes de referência se mantiveram iguais antes/depois (seed `20261102`, 4.096 passos):

- Spikes: `45c47b8e06e2f7dfff2a61832f9d07d5cc4197c8ee35c82df65e3260bbcc92b7`
- Estado: `d34fec09870ee66aa118d91bfc1293c44e9b2fddb14ab6990eb742d330978279`

Testes novos/adaptados cobrem equivalência bit a bit da STDP, reutilização/redimensionamento do buffer de tick, ausência de alias no retorno da rede e equivalência do crédito de ação com índices duplicados, desordenados e inválidos.

A suíte completa no ambiente local (Windows 11, Python 3.14.10, Qt offscreen) coletou **148 testes**: **147 passaram e 1 falhou**. A falha é `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back`: o teste posiciona a janela no limite inferior da tela virtual, onde o clamp impede o salto de 4 px esperado. É uma falha preexistente e fora das mudanças de SNN; nenhum teste foi enfraquecido. A interface em desktop real não foi validada.

## Como reproduzir

No PowerShell, a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --help
.\.venv\Scripts\python.exe benchmarks\component_baseline.py --help
.\.venv\Scripts\python.exe benchmarks\compare_phase2_tick.py
.\.venv\Scripts\python.exe benchmarks\compare_stdp_mark.py
.\.venv\Scripts\python.exe benchmarks\phase2_candidate_benchmarks.py
.\.venv\Scripts\python.exe -m pytest -q -ra --tb=no
```

Os parâmetros completos usados e medições sem arredondamento estão nos JSONs abaixo; os scripts `--help` indicam as opções disponíveis no checkout atual.

## Arquivos de evidência

- Baseline antes: [`phase2_before.json`](../../benchmarks/results/phase2_before.json), [`phase2_before_components.json`](../../benchmarks/results/phase2_before_components.json)
- Benchmark final: [`phase2_after_final.json`](../../benchmarks/results/phase2_after_final.json), [`phase2_after_components_final.json`](../../benchmarks/results/phase2_after_components_final.json)
- Comparação A/B: [`phase2_tick_ab.json`](../../benchmarks/results/phase2_tick_ab.json)
- STDP: [`phase2_stdp_comparison_long.json`](../../benchmarks/results/phase2_stdp_comparison_long.json)
- Crédito de ação e CSR: [`phase2_candidates.json`](../../benchmarks/results/phase2_candidates.json)
- Resultado da suíte: [`validation_phase02.json`](../../benchmarks/results/validation_phase02.json)
- Perfis: [`phase2_before`](../../benchmarks/profile/phase2_before/) e [`phase2_after_final`](../../benchmarks/profile/phase2_after_final/)

## Próximo gargalo

`RewardSTDP.mark`, `SpikingNetwork.step` e a multiplicação CSR seguem no topo do perfil. A meta global de latência ainda não foi atingida. Uma infraestrutura híbrida/Cython pertence à Fase 3 e requer autorização separada; não foi criada nesta entrega.
