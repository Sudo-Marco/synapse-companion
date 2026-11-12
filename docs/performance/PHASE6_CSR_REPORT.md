# Relatório da Fase 6 — propagação CSR compilada

## Resultado

A propagação CSR opcional em Cython agora escolhe entre três caminhos: saída zero
sem spikes, travessia das arestas dos emissores ativos até 30% de atividade, e
travessia CSR por destino quando a atividade é maior. O NumPy/SciPy continua
sendo o padrão. A topologia, os pesos, as equações LIF, o aprendizado, os
snapshots e o fluxo aleatório não foram modificados.

O índice emissor→arestas é criado sob demanda e armazena uma permutação de
arestas e `indptr` em `int32`. Ele não duplica o vetor de pesos. O corte em 30%
foi escolhido após comparar os dois kernels em 126 combinações por plataforma;
em 60% a travessia por destino já é mais consistente e em 100% é claramente
mais rápida.

## Tick completo da rede

Médias de CPU de cinco amostras. Cada amostra mediu 18.000 chamadas a
`SpikingNetwork.step` após 100 ticks de aquecimento. O benchmark usou uma rede
isolada, ruído e entradas fixos; não mede o PetEngine, ferramentas ou UI.

| Plataforma | Neurônios | NumPy CPU (ms/tick) | Cython CPU (ms/tick) | Variação | NumPy parede (ms/tick) | Cython parede (ms/tick) | Hash de spikes |
|---|---:|---:|---:|---:|---:|---:|---|
| Ubuntu | 600 | 0,044366 | 0,022753 | −48,72% | 0,044370 | 0,022755 | `d7768811…068f54` |
| Ubuntu | 1.000 | 0,065446 | 0,027676 | −57,71% | 0,065452 | 0,027678 | `7a8296d0…e8187` |
| Windows | 600 | 0,042535 | 0,021528 | −49,39% | 0,042396 | 0,021235 | `d7768811…068f54` |
| Windows | 1.000 | 0,059896 | 0,025174 | −57,97% | 0,060514 | 0,025143 | `7a8296d0…e8187` |

Os hashes completos coincidem entre NumPy e Cython e entre os sistemas:

- 600 neurônios: `d776881144a3fae953e1e139056cf7b0d4bda2a13702eabdd30bb5a411068f54`
- 1.000 neurônios: `7a8296d01c59226b452fcae3391aaa04cffab562319f89c396fce843e81e8187`

O limite de regressão de CPU de 3% passou em todos os casos; houve melhoria de
48,7% a 58,0%. Em comparação aproximada com o kernel da Fase 5, que ainda usava
CSR NumPy, o tick Cython caiu 54,7–79,5%. Essa comparação entre execuções CI é
indicativa, pois os runners podem variar.

## Seleção de estratégia esparsa

Mediana do speedup do caminho automático sobre SciPy CSR e da travessia por
emissores ativos sobre CSR por destino, em 18 projeções por taxa. Valores acima
de 1 indicam o primeiro caminho mais rápido. Em zero spikes, o caminho
automático retorna zero sem executar um kernel de propagação.

| Spikes ativos | Auto / SciPy — Ubuntu | Ativos / CSR — Ubuntu | Auto / SciPy — Windows | Ativos / CSR — Windows | Caminho automático |
|---:|---:|---:|---:|---:|---|
| 0% | 9,09× | — | 8,21× | — | zero |
| 1% | 3,49× | 4,76× | 3,04× | 2,70× | emissores ativos |
| 5% | 3,19× | 2,90× | 2,76× | 2,03× | emissores ativos |
| 15% | 2,54× | 1,78× | 2,23× | 1,56× | emissores ativos |
| 30% | 1,90× | 1,22× | 1,85× | 1,18× | misto por taxa observada |
| 60% | 1,69× | 0,83× | 1,47× | 0,87× | CSR por destino |
| 100% | 1,36× | 0,68× | 1,30× | 0,69× | CSR por destino |

O corte é aplicado à taxa real de spikes, então alguns casos solicitados em 30%
ficaram ligeiramente acima e usaram CSR por destino. As duas implementações
Cython foram bit a bit iguais em todos os casos do benchmark.

## Memória e custos de construção

- Índice por origem: 7.288 a 331.108 bytes, mediana de 40.066 bytes nas
  projeções avaliadas; criado apenas quando necessário.
- Tempo de construção mediano: 0,36 ms no Ubuntu e 0,32 ms no Windows. É custo
  de reconstrução da projeção, não por tick.
- O vetor de pesos permaneceu compartilhado em todos os casos; não há segunda
  cópia completa dos pesos.
- Pico Python rastreado no benchmark esparso: até 5.403 bytes no Ubuntu e
  5.395 bytes no Windows. RSS é do processo inteiro e inclui as bibliotecas.

## Problemas encontrados e ajustes

Uma primeira medição mostrou que validar todos os vetores CSR em cada chamada
adicionava overhead Python suficiente para mascarar parte do ganho. A validação
foi movida para reconstrução/vinculação da projeção e seu resultado é
armazenado. A primeira escolha do corte também foi revista: medições nas taxas
altas foram inconsistentes para a travessia ativa; o corte final conservador de
30% seleciona CSR por destino a partir de 60% e preserva a vantagem de fontes
ativas na faixa esparsa.

## Validação e limites

- CI no commit `a292eae`: suíte completa e compilação Cython passaram em
  Windows e Ubuntu; os quatro checks do PR ficaram verdes.
- Testes locais: `pytest` — 152 passaram, 3 foram pulados por extensões nativas
  indisponíveis no ambiente local. O teste de determinismo também passou.
- Tradução Cython, `compileall` e `git diff --check` passaram localmente. Não
  havia compilador nativo disponível localmente; os builds nativos foram
  validados pelos jobs de CI.
- Os benchmarks medem redes sintéticas isoladas, não a aplicação completa.
  GUI em desktop Windows físico e comportamento visual não foram validados.
- O backend padrão continua `numpy`; é preciso instalar/compilar o extra
  `native` e selecionar `cython` para usar os kernels compilados.

## Dados brutos

- [`cython_phase6_ubuntu_lif.json`](../../benchmarks/results/cython_phase6_ubuntu_lif.json)
- [`cython_phase6_ubuntu_sparse.json`](../../benchmarks/results/cython_phase6_ubuntu_sparse.json)
- [`cython_phase6_windows_lif.json`](../../benchmarks/results/cython_phase6_windows_lif.json)
- [`cython_phase6_windows_sparse.json`](../../benchmarks/results/cython_phase6_windows_sparse.json)

PR da fase: [#4 — Fase 6: propagação CSR compilada com Cython](https://github.com/Sudo-Marco/synapse-companion/pull/4). Ela está aberta e não foi mesclada.
