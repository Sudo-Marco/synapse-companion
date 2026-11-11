# Relatório da Fase 5 — kernel LIF Cython

## Resultado

Foi adicionado um kernel LIF opcional em Cython. NumPy continua sendo o backend
padrão. A topologia, os parâmetros, a regra LIF, os pesos, a persistência e a
SNN padrão não foram alterados. CSR, crédito por ação e homeostase continuam em
NumPy. A Fase 6 não foi iniciada.

CI compilou os kernels STDP e LIF e passou a suíte completa em Windows e Ubuntu.
Os testes comparam estados, spikes e RNG bit a bit; o teste da rede completa usa
600 e 1.000 neurônios. Os hashes de saída coincidiram entre NumPy e Cython e
entre os dois sistemas:

| Neurônios | SHA-256 da sequência de spikes |
|---:|---|
| 600 | `d776881144a3fae953e1e139056cf7b0d4bda2a13702eabdd30bb5a411068f54` |
| 1.000 | `7a8296d01c59226b452fcae3391aaa04cffab562319f89c396fce843e81e8187` |

## Custo por tick

Média de cinco amostras, em milissegundos por `SpikingNetwork.step`. Cada
amostra cronometrada executou 18.000 ticks após aquecimento, para reduzir a
quantização do relógio de CPU no Windows.

| Plataforma | Neurônios | NumPy CPU | Cython CPU | Δ CPU | NumPy parede | Cython parede | Δ parede |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ubuntu | 600 | 0,055414 | 0,050199 | −9,41% | 0,055421 | 0,050204 | −9,41% |
| Ubuntu | 1.000 | 0,084980 | 0,079440 | −6,52% | 0,084987 | 0,079447 | −6,52% |
| Windows | 600 | 0,091319 | 0,082986 | −9,13% | 0,092012 | 0,083110 | −9,68% |
| Windows | 1.000 | 0,132292 | 0,122743 | −7,22% | 0,133007 | 0,123264 | −7,33% |

O benchmark exige regressão média de CPU de no máximo 3%; os dois jobs passaram.
Ele usa uma rede isolada com o total de neurônios informado, ruído `0.025` e
entradas sintéticas fixas. Não é uma medição do tick completo do app com engine,
ferramentas dinâmicas ou UI.

## Memória e atividade observada

| Neurônios | Pico Python NumPy | Pico Python Cython | Spikes sensores / ocultos / saída em 600 ticks |
|---:|---:|---:|---:|
| 600 | 6.767 B | 6.739 B | 358 / 0 / 0 |
| 1.000 | 10.687 B | 10.339 B | 579 / 0 / 0 |

O pico é `tracemalloc` durante o benchmark, não inclui alocações nativas. O RSS
é do processo inteiro: variação Ubuntu **25.014.272 B**; Windows
**16.891.904 B**. Não deve ser interpretado como memória consumida pelo kernel.

Neste protocolo sintético, os neurônios ocultos e de saída não dispararam em
nenhum backend; apenas os sensores dispararam. A comparação comprova equivalência
do kernel, não eficácia de aprendizado ou cobertura dos estados da SNN. Não
ajustamos limiares, pesos ou estímulos, pois isso mudaria o escopo da Fase 5.

## Validação e limites

- GitHub Actions: compilação, suíte e benchmark passaram em `windows-latest` e
  `ubuntu-latest` (Python 3.12).
- Local: tradução dos `.pyx`, `compileall`, CLI do benchmark e `git diff --check`
  passaram. A suíte reportou **157 passaram, 2 pulados e 1 falha**.
- A falha local foi `test_floating_pet_switches_to_panel_and_back`, no salto da
  UI headless. Ela já ocorria antes da Fase 5 na árvore local com alterações de
  interface não incluídas nesta branch; o CI limpo passou sem essa falha.
- O ambiente local não tem MSVC, então a compilação nativa local não foi feita.
  Os builds nativos usados para confirmar a implementação foram os jobs do CI.
- Nenhuma validação de GUI em desktop Windows físico foi feita.

Branch: `feat/cython-lif-phase5`. PR: [#3 — Cython LIF](https://github.com/Sudo-Marco/synapse-companion/pull/3), encadeado sobre a branch da Fase 4.
