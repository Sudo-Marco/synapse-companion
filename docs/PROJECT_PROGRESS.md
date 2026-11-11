# Progresso da evolução do Synapse Pet

Atualizado em **11 de novembro de 2026**.

## Estado do trabalho

| Fase | Status | Evidência |
|---|---|---|
| 0 — Auditoria da arquitetura real | Concluída no checkout atual | `docs/architecture/CURRENT_ARCHITECTURE.md`, `TECHNICAL_DEBT.md`, `REPOSITORY_INVENTORY.json` |
| 1 — Baseline e profiling | Concluída no checkout atual | `benchmarks/results/baseline.json`, `baseline_components.json`, `baseline_report.md`, `benchmarks/profile/` |
| 2 — Otimização Python | Concluída com ressalva de validação UI headless | `docs/performance/PHASE2_OPTIMIZATION_REPORT.md`; alterações locais no buffer de tick/STDP e crédito de ação |
| 3 — Infraestrutura híbrida | Concluída com limites medidos | `docs/performance/PHASE3_BACKEND_REPORT.md`, testes e benchmark; NumPy padrão, Cython ainda faz fallback |
| 4 — STDP compilada | Implementação pronta; validação nativa pendente | `docs/performance/PHASE4_STDP_REPORT.md`, workflow Cython e testes condicionais |
| 5+ — LIF compilado e evolução | Não iniciadas | Dependem de equivalência e benchmark aprovados da Fase 4 |

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

**Checkpoint da Fase 4:** implementados kernels Cython para marcação STDP e aplicação de recompensa com clipping/Lei de Dale, fallback para arrays não contíguos e build opt-in. Testes locais do contrato: 10 passaram; testes nativos foram pulados porque a compilação está indisponível neste Windows. A suíte integral mantém a falha visual headless preexistente. A conclusão depende de CI Windows/Linux, equivalência bit a bit e benchmarks comparativos; não iniciar Fase 5 antes disso.
