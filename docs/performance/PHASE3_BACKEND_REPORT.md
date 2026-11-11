# Relatório da Fase 3 — infraestrutura de backend neural

**Status:** integração da infraestrutura concluída; validação headless registrada abaixo.
**Data:** 11 de novembro de 2026.
**Escopo:** introduzir seleção e interface de backend em Python, com NumPy como referência e fallback seguro. Não implementar kernels Cython (Fase 4 em diante).

## O que foi criado

- `src/synapse_pet/neural_backend/interface.py`: contrato de LIF, propagação, STDP, recompensa, crédito por ação e homeostase.
- `numpy_backend.py`: adaptador que chama as operações já existentes, sem copiar fórmulas ou alterar a ordem numérica.
- `cython_backend.py` e `factory.py`: seleção explícita e fallback informado. Nesta fase Cython ainda não tem kernels executáveis.
- `configs/default.yaml`: configuração `engine`, `fallback`, precisão e determinismo. NumPy é o padrão.
- `pyproject.toml`: extra opcional `native` com Cython; não é dependência da instalação padrão.
- `SpikingNetwork`, `PetEngine` e replay do sono encaminham suas operações numéricas ao backend. Snapshot carregado recebe o backend em memória novamente; nenhum dado ou formato de snapshot foi alterado.

## Seleção e fallback

| `neural_backend.engine` | Resultado nesta fase |
|---|---|
| `numpy` | Ativa o adaptador NumPy de referência. |
| `cython` | Seleção solicitada fica registrada; como ainda não há kernels, ativa NumPy e registra o motivo. |
| `auto` | Tenta Cython; como não há kernels, ativa NumPy e registra o motivo. |

Precisão diferente de `float32`, valor de backend desconhecido ou fallback diferente de `numpy` falha com erro explícito. O estado de seleção é registrado pelo logger do engine. Instalar o extra Cython, sozinho, não habilita kernels.

## Testes e determinismo

Os novos testes verificam: valores padrão do YAML, seleção/fallback, rejeição de configuração inválida, trajetória da rede exatamente igual entre chamadas diretas e adaptadas, e igualdade de traces/elegibilidade/pesos após STDP, recompensa e crédito por ação.

O teste de hash congelado continuou passando. Com seed `20261102` e 4.096 passos, hashes antes/depois seguem iguais:

- Spikes: `45c47b8e06e2f7dfff2a61832f9d07d5cc4197c8ee35c82df65e3260bbcc92b7`
- Estado: `d34fec09870ee66aa118d91bfc1293c44e9b2fddb14ab6990eb742d330978279`

## Custo do backend NumPy selecionado

Benchmark completo de 1.000 ticks, comparado à medição pós-Fase 2. As duas medições reportaram 1.802 MHz para a frequência instantânea do processador. CPU e parede são medidas separadas.

| Rede | CPU média antes → Fase 3 | Parede média antes → Fase 3 | Delta parede média | Delta P50 | Delta P95 | Delta P99 |
|---|---:|---:|---:|---:|---:|---:|
| 600 solicitados / 712 totais | 12,672 → 12,531 ms | 12,921 → 12,702 ms | −1,69% | −1,88% | +3,36% | +3,63% |
| 1.000 solicitados / 1.112 totais | 25,234 → 25,531 ms | 25,820 → 25,987 ms | +0,65% | −2,33% | +10,73% | +2,56% |

As médias ficaram dentro de +3% nos dois tamanhos e não mostram regressão mensurável atribuível à interface. Os percentis de cauda variaram, em especial P95 da rede de 1.000 (+10,73%); por isso o resultado não é apresentado como prova de latência de cauda inalterada. O desvio-padrão da parede nessa configuração foi 5,08 ms antes e 4,71 ms depois. Uma execução isolada não separa perfeitamente ruído de escalonamento do custo introduzido pelas chamadas de interface.

RSS medido: 600, 56,246 → 56,398 MiB (+0,27%); 1.000, 56,703 → 56,699 MiB (−0,01%). A memória NumPy não indica mudança relevante. O perfil continua dominado por `PetEngine.tick`, STDP e propagação CSR: não há alegação de aceleração por Cython.

## Suíte e limitações

Antes da Fase 3: 148 testes coletados, 147 passaram e 1 falhou. A falha era `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back`, pois o clamp da tela virtual impede o salto de 4 px quando o pet já está no limite inferior. A suíte pós-alteração e a contagem final são registradas em `benchmarks/results/validation_phase03.json`.

Não foi validado em desktop interativo. O backend Cython não executa cálculos nesta entrega; `cython`/`auto` usam NumPy com fallback registrado. Compilação, compartilhamento de memória com memoryviews e equivalência entre Cython/NumPy pertencem às fases de kernels seguintes.

## Reprodução

Na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -ra --tb=no
.\.venv\Scripts\python.exe benchmarks\snn_baseline.py --output benchmarks\results\phase3_backend_numpy.json --compare benchmarks\results\phase2_after_final.json --ticks 1000 --profile-steps 120 --idle-seconds 2 --profile-dir benchmarks\profile\phase3_backend_numpy
```

Resultados completos: [`phase3_backend_numpy.json`](../../benchmarks/results/phase3_backend_numpy.json), benchmark de referência pós-Fase 2: [`phase2_after_final.json`](../../benchmarks/results/phase2_after_final.json), e validação da suíte: [`validation_phase03.json`](../../benchmarks/results/validation_phase03.json).

## Próxima fase

A Fase 4 poderá implementar primeiro STDP compilada atrás deste contrato, comparando traces, elegibilidade, pesos, hashes, custo e RSS. Ela deve manter o fallback NumPy funcional e não alterar a topologia LIF.
