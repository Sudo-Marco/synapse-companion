# Progresso da evolução do Synapse Pet

Atualizado em **11 de novembro de 2026**.

## Estado do trabalho

| Fase | Status | Evidência |
|---|---|---|
| 0 — Auditoria da arquitetura real | Concluída no checkout atual | `docs/architecture/CURRENT_ARCHITECTURE.md`, `TECHNICAL_DEBT.md`, `REPOSITORY_INVENTORY.json` |
| 1 — Baseline e profiling | Concluída no checkout atual | `benchmarks/results/baseline.json`, `baseline_components.json`, `baseline_report.md`, `benchmarks/profile/` |
| 2 — Otimização Python | Concluída com ressalva de validação UI headless | `docs/performance/PHASE2_OPTIMIZATION_REPORT.md`; alterações locais no buffer de tick/STDP e crédito de ação |
| 3 — Infraestrutura híbrida | Concluída com limites medidos | `docs/performance/PHASE3_BACKEND_REPORT.md`, testes e benchmark; NumPy padrão, kernels Cython opcionais para STDP/LIF |
| 4 — STDP compilada | Concluída; equivalência e benchmark no CI Windows/Ubuntu | `docs/performance/PHASE4_STDP_REPORT.md`, artefatos `cython_stdp_ci_*`, workflow e testes |
| 5 — LIF compilado | Concluída; equivalência e benchmark aprovados em CI | `docs/performance/PHASE5_LIF_REPORT.md`, testes, benchmark e CI Windows/Ubuntu |
| 6 — CSR compilado | Validada em CI; PR #4 aberta para `main` | `docs/performance/PHASE6_CSR_REPORT.md`, testes, benchmarks e CI Windows/Ubuntu |
| 7 — Event-driven experimental | Próxima; protocolo definido | Modo fixo continua padrão; experimentar somente sob flag |
| 8+ — evolução | Não iniciadas | Codificação/aprendizado, reorganização arquitetural, persistência/runtime, estresse e release |

## Linha de base atual

- Antes da Fase 2: 600 solicitados / 712 totais com ferramentas: CPU **12,67 ms** e parede **12,82 ms** por tick ativo. Depois: CPU **12,67 ms**, parede **12,92 ms** (+0,75%).
- Antes da Fase 2: 1.000 solicitados / 1.112 totais: CPU **24,80 ms**, parede **25,21 ms**. Depois: CPU **25,23 ms**, parede **25,82 ms** (+2,42%). A frequência reportada variou entre medições (3.201 para 1.802 MHz); ver ressalva no relatório.
- Determinismo de referência: spike SHA-256 `45c47b8e06e2f7dfff2a61832f9d07d5cc4197c8ee35c82df65e3260bbcc92b7`; estado SHA-256 `d34fec09870ee66aa118d91bfc1293c44e9b2fddb14ab6990eb742d330978279`.
- Suíte completa final: **147 passaram, 1 falhou, 148 coletados**. O caso falho é um teste de salto headless limitado pelo fundo da tela virtual; não é mudança do núcleo. O determinismo passou com hashes de spike/estado idênticos à referência.
- Fase 3: após integrar a interface de backend, **157 passaram, 1 falhou, 158 coletados**. A mesma falha visual headless já ocorria antes. Hashes e benchmark comparativo estão em `validation_phase03.json` e `phase3_backend_numpy.json`.

## Checkpoint e próxima ação

As otimizações da Fase 2 não alteraram SNN LIF, topologia, aprendizado, dependências nem persistência. Mudanças preexistentes de sprite/UI foram preservadas. O relatório e os JSONs finais estão em `docs/performance/PHASE2_OPTIMIZATION_REPORT.md` e `benchmarks/results/`.

O bloco de desempenho foi registrado no commit local `3f1bd4e` (`perf: complete Python SNN optimization phase`). Não foi enviado ao remoto e não há PR nesta etapa.

**Checkpoint da Fase 3:** interface integrada ao engine, rede, replay e homeostase; configuração NumPy/Cython/auto, fallback explícito e Cython opcional. O custo médio ficou dentro de 3%; percentis de cauda variaram e estão discriminados no relatório.

**Checkpoint da Fase 4:** kernels Cython para marcação STDP e aplicação de recompensa com clipping/Lei de Dale, fallback NumPy para ausência/layout incompatível e build opt-in. CI compilou e passou a suíte em Windows/Ubuntu; equivalência bit a bit foi confirmada. Marcação acelerou 5,21× no Ubuntu e 6,81× no Windows; aplicação da recompensa, 3,40× e 1,44×. Resultados brutos e ressalvas estão no relatório. A falha local headless preexistente foi mantida e a GUI real não foi validada.

**Checkpoint da Fase 5:** kernel LIF Cython opcional com NumPy como padrão, fallback para layouts incompatíveis/alias, testes bit a bit da população e da rede completa, e benchmark Windows/Ubuntu em 600/1.000 neurônios. CI compilou os módulos, passou a suíte completa e confirmou hashes idênticos; CPU melhorou 6,52% a 9,41% no Ubuntu e 7,22% a 9,13% no Windows. A medição detalhada, memória e atividade por população estão em `docs/performance/PHASE5_LIF_REPORT.md`. A falha local headless anterior permaneceu fora do escopo.

**Checkpoint da Fase 6:** propagação CSR opcional em Cython por destino ou por spikes ativos, com índice fonte→arestas sob demanda e sem duplicar pesos. Layout validado uma vez na reconstrução/vinculação para não adicionar checagens caras em cada tick. O corte final é 30% de atividade: acima dele, CSR por destino é mais consistente. A CI compilou e passou a suíte completa em Windows/Ubuntu; hashes NumPy/Cython coincidiram. CPU do tick caiu 48,7–58,0% contra NumPy, sem regressão. O relatório e quatro JSONs com dados brutos estão em `docs/performance/PHASE6_CSR_REPORT.md` e `benchmarks/results/cython_phase6_*.json`. PR #4 está aberta e não foi mesclada. A compilação nativa local e a UI física do Windows não foram validadas.

**Próxima fase autorizada — Fase 7:** investigar um modo event-driven experimental, sem substituir o passo fixo e sem alterar topologia ou regras de aprendizado. O trabalho começa após o checkpoint da Fase 6; a configuração padrão seguirá `fixed_step`.
