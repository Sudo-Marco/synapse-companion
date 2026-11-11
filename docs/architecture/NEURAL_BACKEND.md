# Interface de backend neural

## Estado

A Fase 3 introduz a seleção e o contrato comum para os cálculos numéricos da SNN. O backend de referência continua sendo NumPy/SciPy e é o padrão. A Fase 3 **não** contém kernels compilados nem declara ganho de desempenho Cython.

## Configuração

O arquivo `configs/default.yaml` contém:

```yaml
neural_backend:
  engine: numpy       # numpy, cython ou auto
  fallback: numpy
  precision: float32
  deterministic: true
```

- `numpy`: usa a implementação atual e determinística como referência.
- `cython`: tenta selecionar o backend opcional; enquanto os kernels das fases seguintes não existem, registra o motivo e usa o fallback NumPy.
- `auto`: tenta o backend Cython e usa o fallback quando indisponível.
- `fallback`: nesta etapa, somente `numpy` é suportado.
- `precision`: somente `float32` é suportado pela implementação atual.
- `deterministic`: transporta a preferência ao backend selecionado. O NumPy continua reproduzindo as operações e a seed existentes.

Configuração desconhecida ou precisão não suportada gera erro claro na inicialização, em vez de ser ignorada. O engine registra a seleção efetiva e qualquer fallback no log rotativo do runtime.

## Contrato e ownership

`src/synapse_pet/neural_backend/interface.py` define as operações de passo LIF, propagação esparsa, marcação STDP, aplicação de recompensa, crédito de ação e homeostase. `numpy_backend.py` delega às implementações atuais sem replicar fórmulas. `SpikingNetwork` possui o backend que usa em cada passo; o `PetEngine` usa a mesma seleção para aprendizado, homeostase e replay durante o sono. Recarregar snapshot reconecta o backend selecionado sem persistir uma escolha de implementação no formato do snapshot.

Arrays permanecem propriedade dos objetos de estado NumPy. A saída de spikes mantém o contrato existente de cópia, e o buffer de corrente é interno à rede. Os backends não devem reter referências ou ponteiros além da chamada.

## Cython opcional

O extra de instalação `native` declara Cython para as próximas fases:

```powershell
python -m pip install -e ".[native]"
```

Instalar Cython, por si só, **não** ativa kernels: nenhum módulo compilado está presente nesta fase. O fallback evita impedir o início do pet em computadores sem compilador/extensão. As operações compiladas serão incorporadas uma a uma nas fases de kernels, com testes de equivalência antes de poderem ser selecionadas como implementação efetiva.

## Validação nesta fase

Testes cobrem seleção explícita NumPy, fallback de `cython`/`auto`, validação de configuração, equivalência exata da trajetória de spikes/voltagens e delegação de STDP/recompensa/crédito. O hash global de determinismo e o custo total do tick devem ser conferidos no relatório da Fase 3. A interface desktop interativa não é validada por estes testes headless.
