# Build opcional do kernel Cython de STDP

O backend padrão do Synapse Pet continua NumPy. A extensão Cython acelera
somente atualização de traços/elegibilidade e aplicação da recompensa da STDP.
LIF, propagação CSR, crédito de ação e homeostase continuam no caminho NumPy.

## Requisitos

- Python suportado pelo projeto.
- Dependências de desenvolvimento e extra `native`.
- Compilador C: MSVC com ferramentas C++ do Visual Studio no Windows; GCC ou
  `build-essential` no Linux.

## Windows / PowerShell

Na raiz do repositório:

```powershell
python -m pip install -e ".[dev,native]"
$env:SYNAPSE_PET_BUILD_CYTHON = "1"
python setup.py build_ext --inplace
Remove-Item Env:SYNAPSE_PET_BUILD_CYTHON
```

O `setup.py` inclui a extensão somente quando
`SYNAPSE_PET_BUILD_CYTHON=1`. Instalar o pacote normalmente não tenta compilar
código nativo.

## Linux

```bash
python -m pip install -e ".[dev,native]"
SYNAPSE_PET_BUILD_CYTHON=1 python setup.py build_ext --inplace
```

## Selecionar e testar

Depois de compilar, defina `neural_backend.engine: cython` na configuração local
do pet e mantenha `fallback: numpy`. Se a extensão estiver ausente ou não puder
ser carregada, o pet inicia pelo backend NumPy e registra o motivo do fallback.

```powershell
python -m pytest -q
python benchmarks/benchmark_cython_stdp.py --output benchmarks/results/cython_stdp_local.json
```

`tests/test_cython_stdp.py` é pulado se a extensão não estiver compilada. O
workflow `.github/workflows/cython-stdp.yml` compila em Windows e Ubuntu,
executa todos os testes e publica o benchmark. CI não valida a GUI no desktop
físico.

## Escopo e limites

Não há OpenMP nem alteração da topologia, parâmetros ou fórmula da SNN. O kernel
recebe memoryviews dos arrays NumPy contíguos existentes; arrays não contíguos
usam a referência NumPy. O backend Cython não deve ser selecionado como padrão
antes de passar nos testes de equivalência.
