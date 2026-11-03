# Synapse Pet

Companheiro virtual local para Windows 10/11. Uma SNN LIF esparsa em NumPy controla um olho expressivo desenhado diretamente em ASCII, em uma cena noturna que acompanha o horário local. A simulação continua em sua própria thread; a interface recebe snapshots imutáveis por uma fila curta para permanecer responsiva.

## Instalação e execução

Requer Python 3.10+ instalado no Windows. No PowerShell, nesta pasta:

```powershell
.\scripts\install.ps1
.\.venv\Scripts\python.exe -m synapse_pet.main
```

Para executar sem interface:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.main --headless --ticks 100
```

Os dados do usuário ficam em `%APPDATA%\synapse_pet`. A configuração padrão está em `configs/default.yaml`.

## Janela e controles

A janela é sem bordas e fica no topo. Arraste pela faixa superior. Os controles principais são:

- **Carinho**: clique no botão ou arraste sobre o olho com o botão esquerdo por pelo menos 1 s (configurável); mover ou clicar sem arrastar só direciona o olhar.
- **Feedback**: registra uma recompensa negativa para o aprendizado.
- **Debug**: mostra taxas neurais, estados afetivos, dopamina e atividade recente.
- **Sensores**: permite ligar cada sensor; todos começam desligados. Monitoramento de arquivos pede uma pasta.
- **Expressões**: alterna a arte ASCII animada e o **HUD**. `M` faz o mesmo, `H` seleciona o HUD, `F11` alterna tela cheia, `T` alterna transparência de 90% e `Escape` sai da tela cheia.
- **Desfazer**: solicita a reversão da última ação compatível com undo.
- **Salvar**: grava o estado atual. Fechar a janela também salva automaticamente.
- **Aceitar / Recusar / Depois**: responde a uma proposta da simulação.
- **— / ×**: minimiza / fecha o aplicativo.

### Saúde da simulação

O save copia o estado na fronteira entre ticks e comprime/grava o snapshot em um worker separado. Erros ficam em `%APPDATA%\synapse_pet\logs\synapse_pet.log`, com rotação de cinco arquivos de até 1 MB. O watchdog monitora o avanço dos ticks; se detectar uma parada, pede uma saída segura, tenta restaurar o último snapshot íntegro e reinicia a thread. O painel DEBUG mostra tick, regime, fila de eventos, propostas pendentes e estado da thread. Propostas sem resposta expiram após `runtime.proposal_timeout_s` (120 s por padrão); `runtime.watchdog_timeout_s` define o limite de inatividade (3 s por padrão).

## Renderização

O renderizador principal usa **PySide6 + QPainter** e compõe cada quadro com glifos monoespaçados em uma grade de caracteres. Ele desenha o olho e o cenário diretamente em ASCII, sem precisar de GPU, OpenGL ou conversão de uma imagem realista. Nuvens deslizam em camadas, estrelas cintilam, vaga-lumes sobem sobre colinas e o reflexo da água ondula. A luz e as cores mudam com a hora local. A interface Qt já gerencia controles, menus, diálogos, atualização visual e a fila que separa a SNN da janela.

O olho usa transições interpoladas, respiração sutil, piscadas simples e duplas, microssacadas e direção do olhar pelo cursor. Os cílios são glifos individuais finos. Estresse reduz a pupila e acrescenta um pequeno tremor; energia controla a abertura e o sono; afeto acrescenta rubor e corações; disparos recentes da rede podem aparecer como pontos de luz. Movimento do olhar, digitação curiosa, mudança de expressão e piscadas aceleram temporariamente a atualização para 30 FPS; sem esses movimentos, ela volta a 5 FPS. O atalho `M` alterna a arte ASCII e o HUD.

### Aprendizado e afeto

O mecanismo mantém affect_impulse separado de learning_rpe. Carinho deliberado gera impulso afetivo; só recompensas explícitas geram RPE e podem alterar pesos. A curiosidade de mouse é um impulso transitório isolado: não chama reward(), não altera RPE e não toca STDP. O movimento é reduzido a quatro categorias (near/far × moving/still), habituadas por repetição e com recuperação lenta; posição bruta nunca vira contexto.

Os limites estão em configs/default.yaml: interaction.affection_drag_min_s controla a duração do arraste; curiosity_novelty configura intensidade, habituação, recuperação e teto por fonte a cada janela móvel de 60 segundos; affect.non_deliberate_mood_per_minute limita ganhos de humor por RPE não deliberado; e mood configura relaxamento. O humor usa componentes rápido (4 min) e lento (30 min), e ganhos positivos diminuem perto de 1.0. O botão CARINHO continua funcionando. Movimento e hover não enviam recompensa nem afeto positivo.

Na pasta do projeto, rode .\.venv\Scripts\python.exe -m synapse_pet.main --reset-affect redefine humor e afeto ao neutro e salva sem apagar pesos aprendidos.
O benchmark de CPU/RAM e a referência determinística ficam em benchmarks/results/. Para medir novamente, use benchmarks/snn_baseline.py; passe --compare para confrontar dois relatórios. Ele mede ticks ativos e ociosos, redes de 600 e 1.000 neurônios, memória e hashes de determinismo.

## Ajustes visuais

Edite o bloco `visual` em `configs/default.yaml`:

```yaml
renderer: ascii      # ascii (direto), cpu (ASCII na CPU) ou auto (compatibilidade GLSL)
visual:
  width: 800         # usado pelo renderer de compatibilidade
  height: 450
  fps_active: 30
  fps_idle: 5
  max_particles: 48
  ascii_columns: 100  # densidade base da grade ASCII
  ascii_rows: 56
  ascii_max_columns: 170  # limite de detalhe para equilibrar nitidez e FPS
  ascii_max_rows: 96
  palette: cyan_amber_white  # compatibilidade GLSL
  scene_time: auto    # auto, noite, dia ou entardecer
  eye_design: A       # A (íris redonda) ou B (olho alongado)
```

`scene_time: auto` usa o relógio local para percorrer noite, amanhecer, dia e entardecer. Escolha `noite`, `dia` ou `entardecer` para fixar a cena durante a revisão da arte. `eye_design: A` usa a íris mais redonda; `B` deixa o olho mais alongado. A grade ASCII acompanha o tamanho físico da janela: ao entrar em tela cheia, aumenta o número de glifos em vez de esticar a mesma imagem. `ascii_columns` e `ascii_rows` ajustam a densidade base; `ascii_max_columns` e `ascii_max_rows` limitam o custo em monitores grandes. Reinicie o app para aplicar mudanças no YAML.

O olhar acompanha o cursor em qualquer ponto da área de trabalho, inclusive fora do olho e da janela do pet. Dentro da janela, a curiosidade recebe apenas categorias grosseiras de movimento, com habituação e limite por minuto; isso não é recompensa nem carinho. Para carinho deliberado, arraste sobre a região do olho pelo tempo mínimo configurado ou use o botão CARINHO. Um clique simples não conta. Quando está curioso, o olho pode seguir por alguns instantes a posição do cursor de texto se ele se mover durante a digitação e o Windows expuser esse ponto. O app consulta apenas a posição do caret: não captura teclas nem lê o texto. Sem interação, o olho passeia suavemente; quando o ciclo de sono começa, fecha os olhos e mostra z animados.

## Capturas e benchmark

O script visual percorre estados emocionais e aberturas das pálpebras nos modos ASCII e HUD e guarda as capturas em `docs/screenshots/`:

```powershell
.\.venv\Scripts\python.exe tools\capture_eye_states.py
.\.venv\Scripts\python.exe tools\capture_eye_states.py --renderer ascii --output docs\screenshots\ascii
```

O benchmark mede FPS e uso médio de CPU em cada modo em operação ativa (alvo 30 FPS) e em repouso (alvo 5 FPS), e tenta consultar VRAM com `nvidia-smi`. Para medir o renderizador ASCII direto:

```powershell
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --seconds 5
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --seconds 3 --size 1920x1080 --output docs\render_benchmark_fullscreen.json
```

O resultado JSON vai para `docs/render_benchmark.json`. O benchmark tenta registrar memória dedicada por processo via WDDM (`process_dedicated_mib`) e usa `nvidia-smi` quando disponível; `system_gpu_mib` é uso total do adaptador, não atribuível apenas ao Synapse Pet. O percentual do processo segue `psutil` e pode passar de 100%; 100% equivale a um núcleo lógico totalmente ocupado. Se nenhuma consulta funcionar, VRAM fica como indisponível.

Para medir o renderer GLSL de compatibilidade com seu fallback QPainter e salvar em um arquivo separado:

```powershell
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --renderer auto --seconds 5 --output docs\render_benchmark_legacy.json
```

No Windows, o benchmark tenta primeiro `nvidia-smi` e depois os contadores de memória dedicada por processo do WDDM. Nos modos ASCII/CPU, o campo dedicado fica em 0 MiB; memória usada pelo compositor do Windows não é atribuída ao avatar.

## Privacidade e permissões

O app não abre conexões de rede. `pynput` conta eventos sem guardar identidade de tecla nem texto. A janela ativa é classificada somente pelo nome do executável; o título não é consultado. O sensor de clipboard emite somente o tamanho quando o conteúdo muda; a ferramenta de histórico guarda conteúdo apenas quando chamada com aceite do usuário. Relatórios de arquivos registram nomes e horários de modificação, nunca o conteúdo.

Ferramentas Python de usuário executam com os privilégios da conta Windows e são código confiável; checagens de caminho não criam isolamento de processo. Ações de risco médio exigem aceite, ações de alto risco pedem confirmação explícita por execução e ações automáticas de baixo risco têm limite por hora.

## Criar uma ferramenta

1. Crie um arquivo Python em `%APPDATA%\synapse_pet\user_tools`.
2. Importe `ToolManifest` de `synapse_pet.tools.manifest`.
3. Defina `run(params)`, valide parâmetros e retorne um dicionário pequeno.
4. Crie `MANIFEST = ToolManifest(...)` com nome, descrição, risco, tags e função.
5. Respeite as pastas e comandos configurados no YAML.
6. Solicite recarga explícita dos plugins antes de usar.

Há um exemplo mínimo em `src/synapse_pet/tools/user_tools/example_plugin.py`.

## Limitações

O renderizador ASCII direto não requer aceleração gráfica. A paleta do cenário é definida no código de `src/synapse_pet/ui/ascii_runtime.py`; o ciclo automático usa o relógio local do Windows. `renderer: auto` ainda mantém o renderizador GLSL anterior para comparação, mas ele não é o avatar padrão. Transparência depende do compositor do Windows. Em janela minimizada/oculta, a renderização para; em repouso, a interface reduz o alvo para 5 FPS. Se o cursor de texto do aplicativo ativo não for exposto pelo Windows, o pet continua seguindo o mouse e os olhares aleatórios. O benchmark informa VRAM indisponível/zero para o modo ASCII executado na CPU.

A dinâmica e a topologia LIF permanecem inalteradas; foram separados os sinais de afeto e RPE e o codificador agora acompanha o número de neurônios sensoriais para permitir redes maiores. A fila visual tem capacidade de um snapshot e descarta o snapshot antigo se a interface estiver atrasada; spikes visuais representam os neurônios ativos no snapshot mais recente, não um histórico de todos os eventos.

## Fase 2 — avaliação de aprendizado

O harness offline usa três contextos (X/Y/Z) e três ferramentas simuladas. Rode-o com:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.sim.learning_eval --output docs\learning
```

Ele não executa ferramentas reais. Nos episódios de treino, 20% das escolhas são exploração; a avaliação usa a escolha gulosa sem feedback. A pontuação combinada corresponde à taxa neural decodificada normalizada por `learning.neural_score_scale_hz`, somada à preferência por contexto/ferramenta. O CSV inclui também a ablação neural-only e a ablação preference-only, para separar o efeito dos pesos da memória do seletor. `action_gate_eligible` mede a saída neural acima do limiar de ferramenta; `production_action_available` também exige iniciativa ≥ 0,5.

Resultados com seed 20261102, 600 neurônios e as taxas selecionadas (crédito de ação 0,10; previsão 0,05):

| Cenário | Política combinada | SNN-only na avaliação |
| --- | ---: | ---: |
| a — simples | 100% | 100% |
| b — reversão | 100%; readaptação em 44 episódios | 100% |
| c — três contextos | X 100%, Y 100%, Z 100% | X 100%, Y 97,5%, Z 77,5% |
| d — 10% de feedback ruidoso | 100% | 100% |
| e — retenção após interferência | 100% | 67% |

A ablação SNN-only desliga a preferência contextual na decisão de avaliação, mantendo o treino normal combinado. Na seleção de taxas, o cenário b também foi treinado com o seletor completamente desligado: a combinação escolhida atingiu 100% após readaptação em 49 episódios. A grade completa de nove combinações está em docs/learning/context_projection_stage/rate_grid.csv.

As projeções de saída são separadas por contexto e alocadas quando o contexto aparece; a matriz CSR e seus índices são compartilhados. A assinatura sensorial inicial permite copiar pesos de um contexto próximo quando o cosseno excede o limite configurado. O YAML define context_projections.max_contexts: 8 e context_projections.similarity_threshold: 0.85; ao exceder o limite, o contexto menos usado é descartado. Os pesos, assinaturas e a ordem LRU são salvos no snapshot. Snapshots v1 migram os pesos de saída antigos para a projeção-base.

A fração do score do vencedor combinada atribuída aos termos normalizados da SNN e da preferência contextual foi: a 43%/57%; b 21%/79%; c X 24%/76%, Y 40%/60%, Z 32%/68%; d 31%/69%; e 29%/71%. São proporções do score, não uma atribuição causal. No cenário e, a política combinada reteve 100%, enquanto a ablação neural teve 67%.

As curvas e CSVs finais por episódio estão em docs/learning/context_projection_stage/; summary.md registra a grade, os cenários, as contribuições e o benchmark. O custo médio ativo foi 9,0104 ms/tick com 600 neurônios antes e depois; com 1.000, foi 18,9583 antes e 18,9063 depois. O delta ficou dentro do limite de +0,20 ms/tick. Os 38 testes passaram, incluindo determinismo, round-trip dos snapshots com contexto e migração v1. Estes são resultados da simulação e do benchmark offline; não representam validação no app real.
