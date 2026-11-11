# Interface de backend neural

## Estado

A Fase 3 introduziu a seleção e o contrato comum para cálculos numéricos da
SNN. A Fase 4 adiciona kernels Cython opcionais para STDP: atualização de
traços/elegibilidade e aplicação da recompensa. A Fase 5 adiciona um kernel
Cython opcional para o passo LIF. O backend padrão continua NumPy; propagação
CSR, crédito por ação e homeostase permanecem no caminho NumPy existente.
A equivalência compilada e o custo da Fase 5 aguardam CI Windows/Ubuntu.

## Configuração

`configs/default.yaml` mantém `engine: numpy`, `fallback: numpy`, precisão
`float32` e determinismo ativado.

- `numpy`: implementação NumPy/SciPy de referência.
- `cython`: usa `_stdp` e `_lif` quando ambas as extensões compiladas estão
  disponíveis; caso contrário, registra a causa e usa o fallback NumPy.
- `auto`: tenta carregar Cython e usa NumPy quando não consegue.
- `fallback`: nesta fase, somente `numpy` é suportado.
- `precision`: somente `float32` é suportado.

Configuração desconhecida ou precisão não suportada gera erro explícito. O
engine registra o backend efetivo e o motivo de fallback no log do runtime.

## Contrato e ownership

`interface.py` define as operações numéricas utilizadas por rede e runtime.
`NumpyBackend` delega as implementações atuais sem replicar fórmulas. O
`CythonBackend` herda esse adaptador e substitui `step_neurons`, `update_stdp`
e `apply_reward`. O LIF mantém a ordem de operações e os arredondamentos
float32 da implementação de referência, além de consumir o mesmo fluxo RNG
quando o ruído está ativo. Os arrays continuam pertencendo aos objetos NumPy;
os kernels usam memoryviews durante a chamada e não armazenam ponteiros. Layouts
incompatíveis e entradas com alias voltam ao caminho NumPy.

Nenhum estado do backend é escrito no snapshot, então saves permanecem
independentes de Cython.

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
`.github/workflows/cython-stdp.yml` compila `_stdp` e `_lif` em Windows e Ubuntu,
executa a suíte com as extensões e publica benchmarks por plataforma.

## Validação

`tests/test_cython_stdp.py` compara bit a bit traços, elegibilidade e pesos
após STDP e recompensa. `tests/test_cython_lif.py` compara a transição LIF e a
trajetória integral da rede em múltiplos tamanhos, incluindo RNG. Os benchmarks
separam tempo de CPU e parede e medem `tracemalloc` e RSS do processo; RSS
representa o processo inteiro, não a extensão isolada. O benchmark LIF cobre a
chamada completa de `SpikingNetwork.step`, incluindo a propagação CSR inalterada.
