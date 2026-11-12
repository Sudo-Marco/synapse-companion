# Interface de backend neural

## Estado

A Fase 3 introduziu a seleção e o contrato comum para cálculos numéricos da
SNN. A Fase 4 adiciona kernels Cython opcionais somente para STDP: atualização
de traços/elegibilidade e aplicação da recompensa. O backend padrão continua
NumPy; LIF, propagação CSR, crédito por ação e homeostase permanecem no caminho
NumPy existente.

## Configuração

`configs/default.yaml` mantém `engine: numpy`, `fallback: numpy`, precisão
`float32` e determinismo ativado.

- `numpy`: implementação NumPy/SciPy de referência.
- `cython`: usa `_stdp` quando a extensão compilada está disponível; caso
  contrário, registra a causa e usa o fallback NumPy.
- `auto`: tenta carregar Cython e usa NumPy quando não consegue.
- `fallback`: nesta fase, somente `numpy` é suportado.
- `precision`: somente `float32` é suportado.

Configuração desconhecida ou precisão não suportada gera erro explícito. O
engine registra o backend efetivo e o motivo de fallback no log do runtime.

## Contrato e ownership

`interface.py` define as operações numéricas utilizadas por rede e runtime.
`NumpyBackend` delega às implementações atuais sem replicar fórmulas. O
`CythonBackend` herda esse adaptador e substitui apenas `update_stdp` e
`apply_reward`. Os arrays continuam pertencendo aos objetos NumPy; o kernel usa
memoryviews contíguas durante a chamada e não armazena ponteiros.

Entradas fora de contiguidade usam a referência NumPy. Nenhum estado do backend
é escrito no snapshot, então saves permanecem independentes de Cython.

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
`.github/workflows/cython-stdp.yml` compila em Windows e Ubuntu, executa a
suíte com a extensão e publica o JSON do benchmark por plataforma.

## Validação

`tests/test_cython_stdp.py` compara bit a bit traces, elegibilidade e pesos
após STDP e recompensa. O benchmark `benchmarks/benchmark_cython_stdp.py`
separa tempo de CPU e parede, mede pico rastreado pelo `tracemalloc` e registra
o RSS do processo. RSS representa o processo inteiro, não a extensão isolada.
LIF, CSR, aprendizado comportamental e GUI não fazem parte desse benchmark.
