# Relatório da Fase 4 — STDP compilada

**Status:** implementação preparada; validação nativa aguarda execução do CI.
**Data:** 11 de novembro de 2026.
**Escopo:** somente STDP; nenhuma alteração na topologia LIF, snapshots ou UI.

## Implementação

- `kernels/stdp.pyx` atualiza traços, elegibilidade e aplica recompensa,
  clipping e Lei de Dale em loops Cython sobre arrays existentes.
- `CythonBackend` herda o adaptador NumPy. Somente `update_stdp` e
  `apply_reward` usam a extensão; arrays não contíguos usam a referência.
- O build nativo é opt-in por `SYNAPSE_PET_BUILD_CYTHON=1`; a instalação
  normal não compila nem exige Cython.
- As flags do compilador desativam contração FP/FMA para preservar os limites
  de arredondamento float32 entre operações.
- NumPy permanece padrão. `cython` e `auto` retornam a NumPy quando a extensão
  não puder ser importada.
- CI compila em Windows/Ubuntu, roda a suíte e publica benchmark por sistema.

## Testes locais

Testes direcionados de determinismo/backend: 11 aprovados e 1 ignorado
(`tests/test_cython_stdp.py`) porque a extensão não foi compilada neste ambiente.
Na suíte integral: 157 aprovados, 1 falhou e 1 foi ignorado.

O ambiente Windows não possui compilador C disponível e o import de Cython foi
bloqueado por Controle de Aplicativo. Não tentei contornar a política. Portanto,
compilação, equivalência nativa e ganho de desempenho **NÃO foram validados
localmente**.

## Benchmarks

| Caminho | Tempo anterior | Tempo atual | Ganho |
|---|---:|---:|---:|
| STDP NumPy | pendente da execução comparativa | — | — |
| STDP Cython | extensão ainda não compilada localmente | — | — |

O workflow publica `artifacts/cython-stdp.json`. Esta tabela deve ser preenchida
com os resultados do artefato após CI; nenhum ganho é alegado antes da medição.

## Problemas conhecidos e próxima ação

- Validar a compilação e equivalência bit a bit em Windows e Ubuntu.
- Analisar os benchmarks dos dois sistemas antes de afirmar aceleração ou
  concluir a fase.
- A suíte completa local continua com a falha headless já conhecida em
  `tests/test_pet_renderer.py::test_floating_pet_switches_to_panel_and_back`;
  ela está fora do escopo STDP e será reportada com o resultado integral.
- Interface desktop interativa **NÃO validada**.

Não iniciar a Fase 5 (LIF compilado) nesta entrega.
