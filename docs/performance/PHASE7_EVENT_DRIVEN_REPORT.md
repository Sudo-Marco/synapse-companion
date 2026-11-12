# Relatório da Fase 7 — avanço event-driven experimental

## Resultado

Foi adicionado um protótipo que agrupa passos apenas em blocos silenciosos e
sem ruído. Ele mantém `fixed_step` como padrão, não altera topologia, pesos,
regras de aprendizado ou snapshots, e recua ao loop fixo sem mutação quando
encontra entrada sensorial, ruído, spike pendente, neurônio refratário, estado
inválido ou fronteira de homeostase.

O protótipo reduz o custo de um bloco sintético totalmente silencioso. Não é um
simulador assíncrono geral: os neurônios continuam em passos discretos, e
qualquer estímulo ou dinâmica que possa produzir um evento usa a referência
fixed-step. Com a configuração distribuída (`background_noise: 0.015`), o
fast-forward não é elegível; para experimentá-lo é necessário ativar a flag e
usar `network.background_noise: 0.0`.

## Comparação em blocos silenciosos

CI mediu 5 repetições de 10 blocos, cada um representando 25 passos de 2 ms,
em uma rede isolada sem ruído, estímulo ou spikes. Valores são milissegundos
por passo neural; a razão é `fixed_step / event_driven`.

| Plataforma | Neurônios | Fixed-step (ms/passo) | Event-driven (ms/passo) | Speedup | Spikes iguais |
|---|---:|---:|---:|---:|---|
| Ubuntu | 600 | 0,310177 | 0,003969 | 78,2× | Sim |
| Ubuntu | 1.000 | 0,646269 | 0,004432 | 145,8× | Sim |
| Windows CI | 600 | 0,425183 | 0,003949 | 107,7× | Sim |
| Windows CI | 1.000 | 0,941662 | 0,004609 | 204,3× | Sim |

O benchmark verifica os spikes e os testes comparam também os estados LIF e os
traços STDP dentro de tolerância float32. A multiplicação de decaimento agrupada
pode diferir alguns ULPs do arredondamento repetido. O modo event-driven é
determinístico para uma seed fixa, mas fixed-step continua sendo a referência
para experimentos e produção.

## Fallback com atividade

O benchmark injeta artificialmente spikes em 1%, 5%, 15% ou 30% dos neurônios
antes de cada bloco. São frações de entrada sintética, não taxas medidas do pet
em uso real. Em todos os casos, o caminho experimental recuou para fixed-step,
pulou zero blocos e produziu os mesmos hashes de spikes da referência.

| Plataforma | Mediana do tempo com fallback / fixed-step | Faixa observada | Hashes iguais |
|---|---:|---:|---|
| Ubuntu | 1,006× | 0,985×–1,019× | Sim, em 600 e 1.000 neurônios |
| Windows CI | 0,997× | 0,991×–1,011× | Sim, em 600 e 1.000 neurônios |

As pequenas diferenças de tempo estão dentro da variação do benchmark; o pior
caso medido ficou abaixo de 2% de overhead. A configuração padrão não chama o
fast-forward.

## Tick completo e determinismo

O benchmark LIF executado no mesmo workflow confirmou os kernels anteriores e
os hashes de referência. Essa tabela compara NumPy e Cython no runner atual;
não é uma comparação pré/pós da Fase 7, pois os runners variam entre execuções.

| Plataforma | Neurônios | NumPy CPU (ms/tick) | Cython CPU (ms/tick) | Variação | Hash de spikes |
|---|---:|---:|---:|---:|---|
| Ubuntu | 600 | 0,088176 | 0,045367 | −48,55% | `d7768811…068f54` |
| Ubuntu | 1.000 | 0,127536 | 0,052944 | −58,49% | `7a8296d0…e8187` |
| Windows CI | 600 | 0,091840 | 0,044444 | −51,61% | `d7768811…068f54` |
| Windows CI | 1.000 | 0,132639 | 0,051389 | −61,26% | `7a8296d0…e8187` |

Os hashes completos coincidem com os de referência registrados na Fase 5 e na
Fase 6. Não houve alteração no código de `SpikingNetwork.step`.

## Validação e limites

- CI no commit `0b7a12d`: **162 passaram, 3 pulados** na suíte padrão, tanto em
  Ubuntu quanto Windows; compilação Cython e benchmark passaram nos dois jobs.
- Os testes incluem configuração padrão desligada, fast-forward comparado com
  25 passos fixos, determinismo com a mesma seed, spike posterior igual e
  fallback sem mutação para seis condições inseguras.
- Localmente, `compileall` e `git diff --check` passaram. `pytest` local não foi
  executado porque o Python disponível neste ambiente não tem NumPy nem pytest.
- O benchmark é uma rede sintética isolada. Não mede o PetEngine completo, a UI
  nem sensores reais. GUI em desktop Windows físico não foi validada.
- Como o ruído padrão é diferente de zero, o modo experimental não acelera a
  configuração distribuída. Reduzir o ruído para habilitá-lo altera a dinâmica
  e não é recomendado para uso normal.

## Dados brutos

- [`phase7_event_driven_ubuntu.json`](../../benchmarks/results/phase7_event_driven_ubuntu.json)
- [`phase7_event_driven_windows.json`](../../benchmarks/results/phase7_event_driven_windows.json)
- [`phase7_cython_lif_ubuntu.json`](../../benchmarks/results/phase7_cython_lif_ubuntu.json)
- [`phase7_cython_lif_windows.json`](../../benchmarks/results/phase7_cython_lif_windows.json)

PR da fase: [#5 — avanço event-driven experimental](https://github.com/Sudo-Marco/synapse-companion/pull/5), empilhada sobre [#4 — CSR compilado](https://github.com/Sudo-Marco/synapse-companion/pull/4). Nenhuma das duas foi mesclada nesta etapa.
