# Synapse Pet

![Status: em desenvolvimento](https://img.shields.io/badge/status-em%20desenvolvimento-orange)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Windows 10/11](https://img.shields.io/badge/plataforma-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-2E8B57)

**Tópicos:** `Python` · `SNN/LIF` · `PySide6` · `arte ASCII` · `simulação local` · `Windows` · `companheiro virtual`

**Synapse Pet** é um companheiro virtual de desktop em desenvolvimento. Uma rede neural de impulsos esparsa (SNN, do inglês *spiking neural network*) controla estados simulados de humor, energia, curiosidade e estresse, que influenciam um olho animado em arte ASCII e uma interface de telemetria.

O projeto é local por padrão e foi estruturado para crescer em etapas. Hoje, ele é uma simulação interativa e um ambiente de experimentação; não é um assistente de linguagem nem um sistema de inteligência geral.

> **Resumo do estado:** a aplicação, a simulação local, a persistência, os controles e as avaliações offline descritas neste documento estão implementados. A suíte automatizada teve **52 testes aprovados** em execução local em **3 de novembro de 2026**. Isso não equivale a validação visual ou operacional do aplicativo em uso real, e o repositório ainda não possui integração contínua configurada.

## Navegação

- [Estado e escopo](#estado-e-escopo)
- [O que o programa faz hoje](#o-que-o-programa-faz-hoje)
- [Instalação e execução](#instalação-e-execução)
- [Controles](#controles)
- [Configuração visual](#configuração-visual)
- [Arquitetura](#arquitetura)
- [Dados, sensores e permissões](#dados-sensores-e-permissões)
- [Testes e avaliações](#testes-e-avaliações)
- [Saídas produzidas](#saídas-produzidas)
- [Direção futura](#direção-futura)
- [Licença](#licença)

## Estado e escopo

| Área | Situação atual |
| --- | --- |
| Aplicativo de desktop | Implementado com PySide6; janela sem bordas, arrastável e sempre no topo. |
| Avatar | Olho animado em ASCII, com HUD alternável, expressões e cenário que acompanha o horário local. |
| Simulação | SNN LIF esparsa, estados afetivos e necessidades, seletor de ações e propostas de ferramentas locais. |
| Salvamento e recuperação | Snapshots, exportação/importação de backup, log rotativo e mecanismos de proteção da thread de simulação. |
| Avaliação de aprendizado | Cenários artificiais reproduzíveis, relatórios CSV/JSON e curvas em PNG. |
| Assistência por linguagem | **Não implementada.** O programa não interpreta perguntas livres nem gera respostas ou código como um modelo de linguagem. |
| Fase 3 do plano de aprendizado | **Não iniciada.** |

### O que o programa faz hoje

- Executa uma simulação de neurônios LIF com topologia esparsa e configuração padrão de 600 neurônios.
- Transforma sinais simulados em métricas como humor, energia, estresse, curiosidade, dopamina e taxa de disparo.
- Anima o olho de acordo com o estado da simulação: olhar, piscadas, expressões, sono e reações a interações deliberadas.
- Mostra um painel de debug com telemetria e saúde da thread de simulação.
- Aprende associações em tarefas delimitadas de avaliação; preferências contextuais participam da seleção de ações.
- Pode propor ferramentas locais, sujeitas às permissões e confirmações configuradas.
- Salva o estado e os pesos aprendidos localmente, sem apagar o aprendizado ao redefinir humor e afeto.

### O que não faz

- Não é um chatbot, copiloto de programação ou mecanismo de busca. Não responde a perguntas abertas como um modelo de linguagem.
- A SNN não compreende texto ou significado geral. As avaliações atuais usam sinais e cenários artificiais definidos pelo projeto.
- Um resultado bem-sucedido na avaliação offline não demonstra que a SNN aprendeu uma habilidade geral nem que o comportamento será igual em outros contextos.
- O programa não toma a simulação como evidência de eficácia no mundo real.

## Instalação e execução

### Requisitos

- Windows 10 ou 11.
- Python 3.10 ou superior, disponível como `python` no PowerShell.
- Acesso à internet durante a instalação para baixar as dependências do projeto.

Abra o PowerShell na pasta do repositório e execute:

```powershell
.\scripts\install.ps1
.\scripts\run.ps1
```

O instalador cria `.venv` e instala o projeto com as dependências de desenvolvimento e os sensores opcionais para Windows. Se o PowerShell bloquear a execução do script, permita a execução apenas na sessão atual e rode novamente:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install.ps1
```

Para iniciar diretamente pelo interpretador do ambiente virtual:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.main
```

Para executar sem abrir a interface gráfica:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.main --headless --ticks 100
```

Esse modo roda uma quantidade definida de ticks e imprime o total executado e o tamanho da rede. Ele serve para verificações da simulação, não para conversar com o pet.

### Comandos úteis

Redefinir humor e afeto ao neutro, preservando os pesos aprendidos:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.main --reset-affect
```

Exportar ou importar um backup portátil da criatura:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.main --export-creature .\backup.zip
.\.venv\Scripts\python.exe -m synapse_pet.main --import-creature .\backup.zip
```

## Controles

| Controle | Função |
| --- | --- |
| **CARINHO** | Envia uma interação afetiva deliberada. Também é possível arrastar sobre o olho pelo tempo mínimo definido em `interaction.affection_drag_min_s` (1 segundo por padrão). |
| Arrastar o cursor sobre o olho | Após o gesto deliberado e o tempo mínimo, envia carinho. Hover ou clique sem arrastar não gera recompensa afetiva positiva. |
| Cursor sobre a área do olho | Direciona o olhar e pode gerar curiosidade breve, categorizada e habituada. Não equivale a carinho nem a recompensa de aprendizado. |
| **FEEDBACK** | Envia um sinal de feedback negativo à simulação. |
| **DEBUG** | Abre o painel de telemetria: estado neural e afetivo, tick, regime, fila e saúde da thread. |
| **SENSORES** | Abre o menu para ativar ou desativar cada sensor. Todos começam desligados. A ativação do monitor de arquivos pede uma pasta. |
| **EXPRESSÕES · ASCII** | Alterna a visualização ASCII e o HUD. |
| **DESFAZER** | Solicita a reversão da última ação que oferece suporte a undo. Não desfaz qualquer mudança da simulação. |
| **SALVAR** | Solicita o salvamento do estado atual. A escrita do snapshot é executada fora do caminho crítico dos ticks. |
| **ACEITAR / RECUSAR / DEPOIS** | Responde a uma proposta de ferramenta apresentada pelo pet. Ações de risco elevado exigem confirmação explícita. |

Atalhos: `M` alterna ASCII/HUD, `H` seleciona HUD, `F11` alterna tela cheia, `T` alterna opacidade entre 100% e 90%, e `Esc` sai da tela cheia. A faixa superior permite arrastar a janela; `—` minimiza e `×` fecha.

## Configuração visual

As opções ficam em [`configs/default.yaml`](configs/default.yaml). O aplicativo lê o arquivo ao iniciar; reinicie-o para aplicar alterações.

| Opção | Efeito |
| --- | --- |
| `renderer` | `ascii` é o padrão e usa o avatar animado em caracteres sem exigir OpenGL. `cpu` atualmente seleciona o mesmo avatar ASCII. `auto` tenta o renderizador OpenGL e recorre ao renderizador QPainter se não conseguir inicializá-lo. |
| `visual.ascii_columns`, `visual.ascii_rows` | Densidade inicial da grade de caracteres. |
| `visual.ascii_max_columns`, `visual.ascii_max_rows` | Limites da grade quando a janela cresce, para equilibrar nitidez e custo de renderização. |
| `visual.scene_time` | `auto` acompanha o relógio local; `noite`, `dia` e `entardecer` fixam a iluminação da cena. |
| `visual.eye_design` | Escolhe entre os desenhos `A` e `B` do olho. |
| `visual.fps_active`, `visual.fps_idle` | Alvos de atualização durante atividade e repouso. A interface pausa a renderização quando oculta ou minimizada. |
| `visual.palette` | Paleta do renderizador de compatibilidade. A arte ASCII padrão define suas próprias cores no código e não usa esta opção como paleta configurável. |
| `context_projections.max_contexts`, `context_projections.similarity_threshold` | Limite de projeções contextuais próprias e similaridade mínima para inicializar uma projeção copiando outra. |

`auto` mantém o caminho OpenGL/GLSL de compatibilidade; a experiência principal do projeto é o avatar ASCII direto. A disponibilidade do OpenGL e do compositor do Windows pode afetar os modos de compatibilidade e a transparência.

## Arquitetura

```text
Sensores opcionais ─┐
Interações da UI ────┼──> fila de eventos ──> thread da simulação (SNN + estado + seletor)
Relógio local ───────┘                                │
                                                     ├──> fila curta de snapshots ──> interface e avatar
                                                     └──> salvamento assíncrono ────> dados locais
```

- **Interface:** PySide6. O avatar ASCII é desenhado diretamente; o modo de compatibilidade tenta OpenGL/GLSL com fallback para QPainter.
- **Simulação:** a rede LIF esparsa, a integração de estado afetivo, as necessidades e a seleção de ações são executadas separadas da thread da interface.
- **Aprendizado:** recompensas e sinais afetivos têm canais distintos. Preferências contextuais complementam a pontuação neural na seleção de ações.
- **Projeções contextuais:** a topologia esparsa é compartilhada; vetores de pesos por contexto são criados sob demanda, limitados por LRU e incluídos nos snapshots.
- **Resiliência:** erros de execução e de salvamento são registrados; um watchdog monitora os ticks e o estado de saúde é apresentado no DEBUG.

## Dados, sensores e permissões

Os dados locais ficam em `%APPDATA%\synapse_pet` — normalmente `C:\Users\<usuário>\AppData\Roaming\synapse_pet`. O diretório contém estado persistido, memória da aplicação e logs. O log rotativo principal fica em `%APPDATA%\synapse_pet\logs\synapse_pet.log`.

Os sensores opcionais são atividade de teclado/mouse, categoria do aplicativo em foco, eventos em uma pasta escolhida, mudança no clipboard e estatísticas do sistema. Todos estão desligados por padrão. O sensor de clipboard informa o tamanho da mudança e não retorna nem persiste o texto; a ferramenta separada de histórico do clipboard pode armazenar texto quando sua captura é solicitada e autorizada.

O aplicativo não depende de um serviço de IA remoto. A ferramenta `abrir_url`, se usada, abre um endereço HTTP(S) no navegador padrão após uma ação explícita do usuário; isso pode acessar a internet. Plugins Python pessoais são código confiável e executam com os privilégios da conta do Windows: as permissões do pet não os isolam em um sandbox de sistema operacional.

## Testes e avaliações

### Suíte automatizada

Execute a suíte a partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

**Último resultado registrado nesta revisão:** 52 testes aprovados em execução local (`pytest -q`, 3 de novembro de 2026). A suíte cobre, entre outros pontos, determinismo, persistência e migração de snapshots, canais de recompensa, habituação da curiosidade, projeções por contexto e resiliência do runtime. Ela inclui verificações headless; não substitui validação manual da interface em outra máquina. Não há workflow de CI configurado neste repositório.

### Avaliação offline da aprendizagem

O simulador reproduz cinco cenários — associação simples, reversão, três contextos, feedback ruidoso e retenção após interferência — sem executar ferramentas reais:

```powershell
.\.venv\Scripts\python.exe -m synapse_pet.sim.learning_eval --output docs\learning
```

O relatório final das mudanças aprovadas está em [`docs/learning/context_projection_stage/summary.md`](docs/learning/context_projection_stage/summary.md), junto com os CSVs, JSON e curvas PNG. Nesse protocolo, a política combinada passou os critérios dos cenários **a–e**, com 100% de acerto combinado; no cenário **b**, a readaptação ocorreu em 44 episódios. Na ablação que remove a preferência contextual, o cenário **c** obteve 100% em X, 97,5% em Y e 77,5% em Z; o cenário **e** obteve 67%. Portanto, os resultados demonstram a contribuição importante do seletor contextual e não devem ser apresentados como sucesso isolado da SNN em todos os cenários.

Os números são específicos do protocolo, seed e configuração registrados nos arquivos de avaliação. São resultados de simulação, sem validação no aplicativo real. A Fase 3 não foi iniciada.

### Benchmarks e capturas

Medir o custo da SNN e comparar duas configurações:

```powershell
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py
```

Medir renderização e gerar um relatório local:

```powershell
.\.venv\Scripts\python.exe benchmarks\render_benchmark.py --seconds 5
```

Capturar os estados visuais do avatar:

```powershell
.\.venv\Scripts\python.exe tools\capture_eye_states.py
```

Os benchmarks dependem do computador e da GPU disponíveis; leituras de VRAM podem não estar disponíveis ou ser atribuíveis somente ao adaptador gráfico, e não ao processo do pet. Resultados anteriores nos diretórios `docs/` são registros daquela execução, não garantias de desempenho em outros equipamentos.

## Saídas produzidas

| Saída | Local padrão | Conteúdo |
| --- | --- | --- |
| Estado do pet | `%APPDATA%\synapse_pet` | Snapshots da rede e dos estados persistidos; backup portátil opcional em ZIP. |
| Log rotativo | `%APPDATA%\synapse_pet\logs\synapse_pet.log` | Diagnósticos e exceções do runtime e do salvamento. |
| Avaliação de aprendizado | `docs/learning/` | CSV e JSON por cenário, além de curvas PNG. |
| Relatório de projeções contextuais | `docs/learning/context_projection_stage/` | Resultados da avaliação final e grade de taxas. |
| Capturas de estados visuais | `docs/screenshots/` | Imagens dos estados de expressão geradas pelo script de captura. |
| Benchmark de renderização | `docs/render_benchmark*.json` | Medições registradas localmente, que variam por hardware. |

## Direção futura

O projeto pretende evoluir como um companheiro local mais expressivo, estável, configurável e capaz de aprender preferências em tarefas bem delimitadas. O caminho de expansão pode incluir:

1. Aumentar a cobertura e a variedade dos protocolos de avaliação antes de ampliar alegações sobre aprendizado.
2. Tornar as ferramentas locais mais úteis, mantendo permissões explícitas e comportamento observável.
3. Melhorar a instalação, distribuição e atualização para Windows.
4. Explorar novos comportamentos, estados e formas de interação do avatar.

Estes itens são objetivos de evolução, não funcionalidades entregues nem um compromisso de prazo. A prioridade é preservar resultados reproduzíveis, separar simulação de alegações sobre capacidades gerais e documentar cada nova etapa.

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).
