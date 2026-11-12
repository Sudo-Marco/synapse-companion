# Checklist da evolução

Legenda: ✅ concluído com evidência; ⚠️ executado com ressalva registrada; ⬜ não iniciado.

## Fase 0 — auditoria

- [x] Registrar branch, commit e alterações preexistentes sem descartá-las.
- [x] Inventariar arquivos/diretórios por caminho e extensão; excluir `.git`, `.venv`, caches, build e `work/` (staging local ignorado).
- [x] Inspecionar os módulos SNN: LIF, rede, CSR, encoding, decoding, STDP, homeostase e neuromodulação.
- [x] Inspecionar todos os módulos `mind/`, o engine/runtime, persistência, sensores, ferramentas e módulos de UI.
- [x] Conferir dependências, pontos de entrada, testes, benchmark existente e workflow CI.
- [x] Documentar fluxo real, equações, persistência, privacidade e limitações em `docs/architecture/CURRENT_ARCHITECTURE.md`.
- [x] Classificar dívida com evidências em `docs/architecture/TECHNICAL_DEBT.md`.

## Fase 1 — baseline e profiling

- [x] Reproduzir o protocolo antigo com 1.000 ticks em 600 e 1.000 neurônios.
- [x] Registrar P50/P95/P99, média e desvio de parede e CPU do tick; anotar resolução temporal da medição de CPU Windows.
- [x] Registrar RSS, bytes de arrays, conexões e contagens/taxas de spikes por população.
- [x] Medir inicialização fria/aquecida, LIF, CSR, STDP, recompensa, homeostase, decoder, ticks ativo/repouso, encoder, crescimento, save e load.
- [x] Registrar alocações `tracemalloc` com a ressalva de que o delta líquido não conta temporários já liberados.
- [x] Gerar perfis cProfile `.prof` e tabela dos gargalos.
- [x] Registrar plataforma, Python, bibliotecas, configuração, seed e referência determinística.
- [x] Propor ordem de otimização Python sem implementar mudanças na SNN.
- [x] Atualizar memória técnica/checkpoint do projeto.
- [x] Confirmar e registrar a falha headless dependente do limite inferior da tela; reproduzida nesta validação, sem ajuste no código ou no teste.

## Fase 2 — otimização Python

- [x] Medir baseline de 1.000 ticks antes das alterações em 600 e 1.000 neurônios.
- [x] Testar conversão de spikes para STDP; descartar variante direta `bool` por ser mais lenta e adotar scratch buffers `float32` reutilizáveis.
- [x] Adicionar teste de equivalência bit a bit para traces/elegibilidade da STDP.
- [x] Reutilizar buffer de corrente em `SpikingNetwork.step`, sem expor memória mutável aos consumidores.
- [x] Comparar `np.isin` e lookup booleano; manter fallback para entradas atípicas e verificar pesos/máscaras exatos.
- [x] Medir alternativa `bincount` para CSR e rejeitá-la por custo/diferença de soma; preservar SciPy CSR.
- [x] Comparar tick completo, memória, hashes e distribuições antes/depois; detalhes em `PHASE2_OPTIMIZATION_REPORT.md`.
- [x] Rodar suíte completa: 147 passaram, 1 falhou (teste UI headless pré-existente por limite inferior da tela virtual).

## Fase 3 — infraestrutura híbrida

- [x] Criar contrato abstrato para passo LIF, propagação, STDP, recompensa, crédito e homeostase.
- [x] Criar adaptador NumPy que delega sem duplicar equações.
- [x] Adicionar seleção `numpy`/`cython`/`auto`, fallback explícito, precisão e preferência determinística.
- [x] Integrar seleção ao engine, step da rede, replay do sono e recuperação por snapshot.
- [x] Declarar Cython como extra opcional; não há kernels compilados nesta fase.
- [x] Confirmar equivalência/determinismo, rodar suíte integral e benchmark de custo; registrar `docs/performance/PHASE3_BACKEND_REPORT.md`.
- [x] Registrar a falha visual headless que já existia antes da fase, sem alterar a asserção.

## Fase 4 — STDP Cython

- [x] Criar kernel compilado para traces/elegibilidade preservando a ordem float32.
- [x] Compilar aplicação de recompensa, clipping e Lei de Dale; deixar crédito por ação no NumPy.
- [x] Manter fallback NumPy, instalação padrão sem compilação e build nativo explicitamente opt-in.
- [x] Adicionar testes bit a bit condicionais e benchmark CPU/parede/memória para update e reward.
- [x] Adicionar CI Windows/Linux para compilar, executar a suíte e gerar artefato de benchmark.
- [x] Confirmar compilação e equivalência nativa nos dois sistemas por CI.
- [x] Medir tempo CPU/parede, alocações rastreadas e RSS de processo; registrar JSONs e relatório.
- [x] Confirmar hash de referência e suíte integral nos jobs CI Windows/Ubuntu; registrar a falha headless local preexistente sem mexer nela.

## Próximas fases — não iniciadas

- [ ] Fase 5: LIF compilado; aguarda autorização explícita para avançar.
- [ ] Fases posteriores: CSR, event-driven, codificação/aprendizado, reorganização e release.
