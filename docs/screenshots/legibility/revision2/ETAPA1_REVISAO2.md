# Revisão 2 — legibilidade ASCII (Etapa 1)

A coluna antiga `Pupila / íris = 4,99:1` media apenas a diferença de luminância entre as duas cores fixas da paleta. Como não comparava pixels do olho com o fundo, repetia o mesmo valor em todos os cenários.

Nesta revisão, `pupila/íris vs fundo` é a mediana da razão WCAG dos pixels visíveis dentro da região circular, após compor a placa sobre o fundo. `borda` é o percentil 5 do melhor contraste local entre o keyline claro e o escuro; o contorno usa os dois tons. O preenchimento pode ficar abaixo de 3:1 em um fundo parecido com sua cor; a borda dupla é a garantia de silhueta sem ler pixels da tela.

O preset `pet.density: normal` mantém os pontos e fibras ASCII como textura; não preenche as células com blocos. Reflexos grandes e médios continuam em glifos ASCII.

As imagens `antes` reutilizam as capturas aceitas da revisão anterior (320×180) reescaladas com vizinho mais próximo para facilitar a comparação em dois tamanhos. As imagens `depois` foram renderizadas diretamente no tamanho de cada pasta. `pequeno` mede uma silhueta de cerca de 60 px de altura; `grande` mede 960×540.

## Contraste — large

| Fundo | Silhueta p05 | Borda da pupila p05 | Borda da íris p05 | Pupila/fundo mediana | Íris/fundo mediana | Pupila/íris interna |
|---|---:|---:|---:|---:|---:|---:|
| preto | 20.43:1 | 20.43:1 | 20.43:1 | 3.95:1 | 3.95:1 | 4.99:1 |
| branco | 19.46:1 | 19.46:1 | 19.46:1 | 1.35:1 | 1.35:1 | 4.99:1 |
| cinza_medio | 4.93:1 | 4.93:1 | 4.93:1 | 1.6:1 | 1.6:1 | 4.99:1 |
| azul_escuro | 17.77:1 | 17.77:1 | 17.77:1 | 3.91:1 | 3.91:1 | 4.99:1 |
| xadrez_ruido | 4.59:1 | 4.63:1 | 4.59:1 | 2.06:1 | 1.76:1 | 4.99:1 |
| foto_paisagem | 5.96:1 | 7.29:1 | 7.82:1 | 2.89:1 | 2.62:1 | 4.99:1 |

## Contraste — small

| Fundo | Silhueta p05 | Borda da pupila p05 | Borda da íris p05 | Pupila/fundo mediana | Íris/fundo mediana | Pupila/íris interna |
|---|---:|---:|---:|---:|---:|---:|
| preto | 20.43:1 | 20.43:1 | 20.43:1 | 3.95:1 | 3.95:1 | 4.99:1 |
| branco | 19.46:1 | 19.46:1 | 19.46:1 | 1.35:1 | 1.35:1 | 4.99:1 |
| cinza_medio | 4.93:1 | 4.93:1 | 4.93:1 | 3.84:1 | 1.6:1 | 4.99:1 |
| azul_escuro | 17.77:1 | 17.77:1 | 17.77:1 | 3.91:1 | 3.91:1 | 4.99:1 |
| xadrez_ruido | 4.59:1 | 4.62:1 | 4.56:1 | 2.53:1 | 1.75:1 | 4.99:1 |
| foto_paisagem | 6.16:1 | 7.54:1 | 7.8:1 | 2.93:1 | 2.62:1 | 4.99:1 |

## Benchmark

Comparação da revisão anterior: ativo 2,511 ms/quadro; repouso 2,727 ms/quadro.

- Depois ativo 30 FPS: 2.705 ms/quadro (8.11% de um núcleo).
- Depois repouso 5 FPS: 2.551 ms/quadro (1.28% de um núcleo).
- A suíte completa `pytest -q`: 83 testes passaram (exit code 0).
