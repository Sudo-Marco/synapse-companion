# Build opcional dos kernels Cython

O backend padrão do Synapse Pet continua NumPy. As extensões Cython opcionais
aceleram o passo LIF e a atualização de traços/elegibilidade e aplicação de
recompensa da STDP. Propagação CSR, crédito de ação e homeostase continuam no
caminho NumPy.

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

O `setup.py` inclui as extensões somente quando
`SYNAPSE_PET_BUILD_CYTHON=1`. Instalar o pacote normalmente não tenta compilar
código nativo.

## Linux

```bash
python -m pip install -e ".[dev,native]"
SYNAPSE_PET_BUILD_CYTHON=1 python setup.py build_ext --inplace
```

## Selecionar e testar

Depois de compilar, defina `neural_backend.engine: cython` na configuração local
do pet e mantenha `fallback: numpy`. Se uma extensão estiver ausente ou nao
puder ser carregada, o pet inicia pelo backend NumPy e registra o motivo do
fallback.

```powershell
python -m pytest -q
python benchmarks/benchmark_cython_stdp.py --output benchmarks/results/cython_stdp_local.json
python benchmarks/benchmark_cython_lif.py --output benchmarks/results/cython_lif_local.json
```

`tests/test_cython_stdp.py` e `tests/test_cython_lif.py` são pulados quando as
extensões opcionais não estão compiladas. O workflow
`.github/workflows/cython-stdp.yml` compila ambos os kernels em Windows e
Ubuntu, executa os testes e publica os benchmarks STDP e LIF. O benchmark LIF
compara ticks completos da rede em 600 e 1.000 neurônios, verifica o hash da
sequência de saídas e mede tempo CPU/parede, memória Python e RSS do processo.
Cada amostra repete a mesma sequência para amortizar a resolução do relógio de
CPU do Windows; o limite de regressão de 3% é aplicado ao tempo CPU, e o tempo
de parede também é registrado. CI não valida a GUI no desktop físico.

## Escopo e limites

Não há OpenMP nem alteração da topologia, parâmetros ou fórmulas da SNN. O kernel
recebe memoryviews dos arrays NumPy contíguos existentes; arrays não contíguos
ou com alias usam a referência NumPy. O backend Cython permanece opt-in e NumPy segue como padrão. A equivalência
e o custo medidos por plataforma estão documentados no relatório da Fase 5.
