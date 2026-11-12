# Relatório da Fase 4 — STDP compilada

**Status:** concluída com equivalência e benchmark no GitHub Actions.
**Data:** 11 de novembro de 2026.
**Commit medido:** `442bdd821a5b1726f7355419397f91c7a2387331`.
**CI:** workflow Cython do PR #2, execução `42977920290` (Windows e Ubuntu).
**Escopo:** somente STDP; nenhuma alteração na topologia LIF, snapshots ou UI.

## Implementação

- `kernels/stdp.pyx` atualiza traços pré/pós, elegibilidade e aplica recompensa,
  clipping e Lei de Dale sobre os arrays NumPy existentes.
- `CythonBackend` herda o adaptador NumPy. Apenas `update_stdp` e
  `apply_reward` usam a extensão; arrays com tipo/layout diferente usam NumPy.
- A instalação normal não compila código nativo. Build Cython é opt-in por
  `SYNAPSE_PET_BUILD_CYTHON=1`.
- `numpy` continua como padrão. `cython` e `auto` usam fallback NumPy quando a
  extensão não pode ser carregada.
- O compilador desativa contração FP/FMA para preservar arredondamentos
  intermediários. A topologia esparsa valida os índices ao reconstruir CSR;
  bounds checks Cython são omitidos no loop quente.

## Equivalência e testes

Os jobs Cython Windows e Ubuntu compilaram a extensão e passaram a suíte
completa. Os testes nativos comparam bit a bit traces, elegibilidade e pesos
após sequências diversas e recompensas positivas/negativas. Os artefatos
registram `exact_equivalence: true` em ambas as plataformas. O workflow normal
de testes do PR também passou.

No ambiente local Windows, os testes direcionados tiveram **11 aprovados e 1
ignorado** (o módulo nativo não pode ser carregado localmente por bloqueio do
Controle de Aplicativo). A suíte integral local teve **157 aprovados, 1 falha e
1 ignorado**. A única falha é `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back`, já conhecida antes desta fase; não foi modificada. A suíte completa remota passou nos dois sistemas.

## Benchmark isolado

Mesma máquina/plataforma por comparação, 17.358 arestas, 712 entradas, 304
saídas, densidade 0,08; 1.200 atualizações por amostra e 7 repetições. Tempos
abaixo são médias por chamada; CPU e parede são reportadas separadamente.

| Operação | Sistema | NumPy CPU / parede | Cython CPU / parede | Aceleração de parede |
|---|---|---:|---:|---:|
| Marcação STDP | Ubuntu | 143,39 / 143,39 µs | 27,52 / 27,52 µs | **5,21×** |
| Marcação STDP | Windows | 219,49 / 219,87 µs | 29,76 / 32,30 µs | **6,81×** |
| Aplicar recompensa | Ubuntu | 60,60 / 60,60 µs | 17,82 / 17,82 µs | **3,40×** |
| Aplicar recompensa | Windows | 66,96 / 75,35 µs | 52,08 / 52,17 µs | **1,44×** |

Pico rastreado pelo `tracemalloc` durante a sequência de marcação: **287.048 B
NumPy → 80.128 B Cython** (−72,1%). RSS ao fim do processo inteiro: 60,9 MiB
Ubuntu e 51,8 MiB Windows; é memória total do runner/processo, não delta
atribuível ao kernel.

Resultados brutos: [`cython_stdp_ci_ubuntu_2026-11-11.json`](../../benchmarks/results/cython_stdp_ci_ubuntu_2026-11-11.json) e [`cython_stdp_ci_windows_2026-11-11.json`](../../benchmarks/results/cython_stdp_ci_windows_2026-11-11.json). Eles incluem o ID do CI e o commit medido.

O ganho foi medido para os kernels STDP. **Não foi medido o ganho no tick completo** nesta fase; não há alegação de redução de latência total do pet. O backend NumPy segue sendo o padrão.

## Arquivos e compatibilidade

O build está documentado em [`BUILD_CYTHON.md`](../development/BUILD_CYTHON.md).
O workflow `.github/workflows/cython-stdp.yml` compila em Windows e Ubuntu,
executa a suíte e publica os JSONs de benchmark. Snapshots não mudam e podem
ser carregados sem extensão Cython.

## Problemas conhecidos e próxima fase

- A suíte local segue com a falha visual headless indicada acima; CI integral
  Windows/Ubuntu passou.
- GUI desktop físico **NÃO validada**.
- A Fase 5 (LIF compilado) não foi iniciada.
