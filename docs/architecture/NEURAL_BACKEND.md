# Interface de backend neural

## Estado

A Fase 3 introduziu a seleção e o contrato comum para cálculos numéricos da
SNN. A Fase 4 adicionou kernels Cython opcionais para STDP, a Fase 5 para LIF
e a Fase 6 para propagação CSR com duas estratégias de travessia. O backend
padrão continua NumPy; crédito por ação e homeostase continuam no NumPy.

## Configuração

`configs/default.yaml` mantém `engine: numpy`, `fallback: numpy`, precisão
`float32` e determinismo ativado.

- `numpy`: implementação NumPy/SciPy de referência.
- `cython`: usa `_stdp`, `_lif` e `_sparse` quando as extensões compiladas
  estão disponíveis; caso contrário, registra a causa e usa o fallback NumPy.
- `auto`: tenta carregar Cython e usa NumPy quando não consegue.
- `fallback`: nesta fase, somente `numpy` é suportado.
- `precision`: somente `float32` é suportado.

Configuração desconhecida ou precisão não suportada gera erro explícito. O
engine registra o backend efetivo e o motivo de fallback no log do runtime.

## Contrato e ownership

`interface.py` define as operações numéricas utilizadas por rede e runtime.
`NumpyBackend` delega as implementações atuais sem replicar fórmulas. O
`CythonBackend` herda esse adaptador e substitui `step_neurons`, `update_stdp`,
`apply_reward` e `propagate`. Para CSR, usa travessia por fonte ativa até 30% de
atividade e travessia por linha para atividade mais densa; sem spikes retorna
um vetor zero. O LIF mantém a ordem de operações e os arredondamentos
float32 da implementação de referência, além de consumir o mesmo fluxo RNG
quando o ruído está ativo. Os arrays continuam pertencendo aos objetos NumPy;
os kernels usam memoryviews durante a chamada e não armazenam ponteiros. Layouts
incompatíveis e entradas com alias voltam ao caminho NumPy.

Nenhum estado do backend é escrito no snapshot, então saves permanecem
independentes de Cython.

## Avanço event-driven experimental

O modo padrão é `simulation.mode: fixed_step` com `simulation.event_driven:
false`. O protótipo de avanço event-driven só tenta agrupar um bloco quando a
rede está silenciosa, não há ruído nem corrente sensorial, todos os neurônios
estão fora da refratariedade e o bloco não cruza uma janela de homeostase.
Qualquer condição não comprovada cai no loop fixo sem alterar estado. Por isso,
o protótipo só pode ser exercitado com `network.background_noise: 0.0` e uma
entrada silenciosa; com a configuração distribuída (`background_noise: 0.015`)
ele usa o caminho fixo.

Para experimentar, configure `simulation.mode: event_driven`,
`simulation.event_driven: true` e ruído zero. O cálculo agrupado é determinístico
e preserva os spikes nos casos testados, mas as multiplicações float32 dos
estados internos podem diferir alguns ULPs do arredondamento repetido. O passo
fixo continua sendo a referência e o modo experimental não é recomendado para
execução normal. Não altera topologia, regras de aprendizado nem snapshots.

## Build Cython opcional

Instalação e compilação são separadas. O pacote padrão nunca tenta compilar
código nativo:

```powershell
python -m pip install -e ".[dev,native]"
$env:SYNAPSE_PET_BUILD_CYTHON = "1"
python setup.py build_ext --inplace
Remove-Item Env:SYNAPSE_PET_BUILD_CYTHON
```

É necessário MSVC com ferramentas C++ no Windows ou GCC/build-essential no
Linux. Instruções completas estão em
[`BUILD_CYTHON.md`](../development/BUILD_CYTHON.md). O workflow
`.github/workflows/cython-stdp.yml` compila `_stdp`, `_lif` e `_sparse` em
Windows e Ubuntu, executa a suíte com as extensões e publica benchmarks por
plataforma.

## Validação

`tests/test_cython_stdp.py` compara bit a bit traços, elegibilidade e pesos
após STDP e recompensa. `tests/test_cython_lif.py` compara a transição LIF e a
trajetória integral da rede em múltiplos tamanhos, incluindo RNG.
`tests/test_cython_sparse.py` compara as estratégias CSR bit a bit, verifica a
indexação fonte→destino sob demanda e a seleção por atividade. Os benchmarks
separam tempo de CPU e parede e medem `tracemalloc` e RSS; RSS representa o
processo inteiro, não a extensão isolada. O benchmark de tick completo cobre
`SpikingNetwork.step` e aplica o limite de regressão de 3%. Os resultados da
Fase 6 estão em [`PHASE6_CSR_REPORT.md`](../performance/PHASE6_CSR_REPORT.md).
