# Dívida técnica observada

Escopo da lista: código e testes do checkout auditado em 8 de novembro de 2026, incluindo as otimizações localizadas da Fase 2. Itens classificados por impacto e evidência; não inclui trabalho da Fase 3.

## P1 — investigar antes de otimização/escala

### P1.1 O tick atual está acima das referências de desempenho

No benchmark antes da Fase 2, 1.000 ticks mediram 12,67 ms de CPU média/tick para 600 neurônios e 24,80 ms para 1.000. Após as otimizações, a média de parede variou +0,75% (600) e +2,42% (1.000), abaixo do limite de regressão de 3%; a CPU média ficou 0,00% e +1,76%. Os artefatos v0.3 históricos registram 9,00 ms e 18,72 ms, respectivamente, sem dados suficientes de hardware para uma comparação causal. A frequência reportada pelo sistema caiu de 3.201 MHz no baseline para 1.802 MHz após, portanto a comparação antes/depois não é perfeitamente controlada; ver `docs/performance/PHASE2_OPTIMIZATION_REPORT.md`.

### P1.2 STDP concentra a maior parte do perfil de tick

No `cProfile` de 120 ticks ativos (3.000 subpassos, 9.000 chamadas a `mark`), `RewardSTDP.mark` consumiu 1,055 s cumulativos; `network.step`, 0,423 s; `SparseProjection.currents`, 0,228 s. Os tempos cumulativos se sobrepõem por chamada aninhada, portanto não devem ser somados. A Fase 2 experimentou buffers reutilizáveis em `mark`: comparação isolada ficou aproximadamente 0,5% mais rápida em parede, sem ganho robusto no tick completo. STDP continua sendo o maior gargalo medido e deve ser alvo de otimizações mais profundas somente com equivalência e profiling.

### P1.3 A afirmação “RPE é o único caminho que altera pesos” não descreve literalmente o código

RPE modula `RewardSTDP.apply_reward` e a recompensa de ação, mas `Homeostasis.update` também escala projeções em ±2% quando a taxa global sai da faixa e `SleepConsolidator.consolidate` poda/regenera arestas e realiza replay de aprendizado. Esses mecanismos são distintos: homeostase/sono não são sinais RPE, mas alteram pesos ou topologia. Se “único sinal” for requisito semântico estrito, a regra precisa ser esclarecida antes de mudar o núcleo; não foi alterada nesta etapa.

## P2 — custo, escalabilidade e fidelidade

### P2.1 Alocações repetidas no hot path

`SpikingNetwork.step` cria `current = np.zeros(...)` a cada subpasso, recebe vetores temporários das três multiplicações CSR e faz soma/escala. O engine chama a rede até 25 vezes por tick ativo. `LIFPopulation.step` também retorna cópia do vetor de spikes. O perfil mede chamadas a `numpy.zeros`, `astype` e matmul; otimizar buffers exige definir ownership e preservar snapshots/filas sem data races.

### P2.2 STDP e crédito de ação criam vetores por aresta

`RewardSTDP.mark` converte spikes para `float32`, indexa traços pelas arestas e atualiza elegibilidade. A Fase 2 agora reutiliza dois buffers `float32` por objeto STDP; testes comparam bit a bit traces e elegibilidade contra a fórmula anterior. `apply_action_credit` substitui `np.isin` por lookup booleano apenas quando os índices são inteiros e estão no intervalo válido; o fallback preserva os casos atípicos. Teste e benchmark confirmam máscaras e pesos exatamente iguais, com cerca de 24% menos tempo de parede no microbenchmark do crédito de ação.

### P2.3 Inicialização/crescimento usam máscaras densas temporárias

`SparseProjection.random`, `SpikingNetwork.add_tool_group` e caminhos de expansão geram matrizes aleatórias densas antes de extrair conexões com `nonzero`. Embora a representação persistida seja CSR, a memória transitória de construção escala com `n_pre × n_post`. O crescimento 600→800 mediu cerca de 4,96 ms na cópia de rede preparada, excluindo a cópia do template. Avaliar conectividade esparsa direta antes de redes muito maiores.

### P2.4 Resume de snapshot não representa todo estado transitório

Snapshot v2 persiste pesos/topologia, contexto, RNG e estado LIF, além do estado cognitivo listado no JSON. Não captura traços/elegibilidade de `RewardSTDP`, os acumuladores de janela da homeostase, os valores EMA internos do decoder nem os temporizadores transitórios de sleep. A retomada restaura estado persistente, mas não reproduz exatamente uma simulação interrompida no mesmo subpasso.

### P2.5 Um único sinal global de homeostase

Homeostase mede média de disparos do conjunto, aplica ajustes no limiar base da população e escala as três projeções. Isso não diferencia populações (sensor/oculta/saída) nem contexto. Os benchmarks mostram taxas muito diferentes por população em alguns registros históricos curtos; validar estabilidade em sessão longa antes de alterar regras.

### P2.6 UI e engine concentram muitas responsabilidades

`runtime/engine.py` tem cerca de 1.100 linhas; `ui/qt_app.py`, cerca de 2.440. O engine coordena rede, mente, sensores, ferramentas, thread, watchdog, snapshots e eventos; a janela Qt coordena painéis, sensores, bandeja, renderização, desktop motion, saltos, teleporte e post-its. A Fase 2 não reorganizou esses módulos; mudanças futuras devem ser isoladas e guiadas por testes.

### P2.7 Interface legada coexistindo com Qt

`main.py` abre PySide6, mas `ui/app.py`, `ui/avatar.py` e `ui/bubble.py` ainda contêm implementação Tkinter. A duplicidade amplia superfície de manutenção e pode confundir documentação de entrada. Não remover nada sem confirmar referências e compatibilidade.

### P2.8 Reprodutibilidade histórica incompleta

O baseline v0.3 guarda Python, NumPy e métricas, mas não o modelo do processador, frequência, SciPy, plano de energia ou estado de carga. O novo `baseline.json` registra essas informações disponíveis. O hash determinístico atual coincide com o baseline v0.3; os JSONs de fase anteriores (`snn_baseline_phase0/phase1`) têm hashes mais antigos. Comparações precisam escolher a referência correta e registrar versão/commit.

### P2.9 Falha na suíte headless neste ambiente

Execução local pós-Fase 3: **157 passed, 1 failed, 158 coletados**. Falhou `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back`, na asserção de que o salto triste com amplitude 4 px mova a janela para baixo. A geometria foi posicionada no limite inferior da área de trabalho offscreen; `_jump_frame` passa a posição por `_clamp_pet_position`, que limita o movimento. A falha depende da geometria simulada do display e não está relacionada ao núcleo SNN. O mesmo teste falhava antes da Fase 3; nenhum código/UI ou asserção desse teste foi alterado nesta fase. Ver `benchmarks/results/validation_phase03.json`.

## P3 — produto e manutenção

- `SleepConsolidator.update` recebe `on_ac_power`, mas o valor não participa da lógica atual.
- O custo de primeira construção da SNN inclui importação lazy de SciPy (`SparseProjection.rebuild`); o benchmark mede cerca de 323 ms na primeira instância e cerca de 3,63 ms em construções já aquecidas neste processo.
- Custo de áudio, GPU/VRAM e renderizadores não é incluído no benchmark SNN. O núcleo é CPU/NumPy; a GUI foi executada apenas em testes offscreen.
- `moderngl`, `PySide6` e Pillow estão declarados como dependências obrigatórias, apesar de caminhos alternativos CPU/ASCII. O fallback do renderer não torna todos esses pacotes opcionais para instalação do projeto.

## Alterações e limites das fases 2 e 3

Na Fase 2 foram alterados buffers internos da rede/STDP e o lookup do crédito de ação; na Fase 3, as chamadas numéricas passaram por uma interface comum e configuração NumPy/Cython/auto. Equações, topologia, taxa de aprendizado, densidade, API/formato de persistência e sensores permaneceram iguais. O buffer de `current` é interno à thread da SNN, e a saída continua copiada para evitar alias mutável. A tentativa de substituir CSR por `numpy.bincount` foi rejeitada: além de ser mais lenta no benchmark local, não reproduziu o hash bit a bit. A Fase 3 cria seleção/fallback e contrato, mas não kernels compilados; custo e determinismo após a integração precisam ser registrados no relatório próprio da Fase 3.
