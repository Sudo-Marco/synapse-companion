# Renderização do olho ASCII

O renderizador seleciona detalhes pela altura física da janela PET. A resolução interna usa células de pelo menos 8 px, configuráveis em `pet.outline.min_cell_px` (valores menores são limitados a 8 px para preservar a leitura dos glifos). O LOD pequeno é usado abaixo de 112 px, o médio entre 112 e 223 px e o grande a partir de 224 px. Uma interpolação suave ajusta tamanho e quantidade de textura perto das transições.

No LOD pequeno, uma grade analítica 4×4 define a máscara arredondada e as métricas de cobertura; QPainter desenha a esclera, a íris, a pupila e dois reflexos como base vetorial suave. Glifos ASCII finos e fibras radiais ficam por cima, com baixa densidade, sem formar faixas de blocos. A pupila ocupa pelo menos 3×3 células, o anel da íris tem ao menos uma célula e os reflexos têm o equivalente físico a 2×2 células e 1×1 célula. Os detalhes ASCII entram gradualmente nos LODs médio e grande. O contorno suave de duas cores acompanha a silhueta curva do PET, sem capturar pixels da área de trabalho.

## Configuração

Em `configs/default.yaml`:

- `pet.density`: `bold`, `normal` ou `fine` controla a frequência dos glifos de preenchimento e textura.
- `pet.outline.min_cell_px`: dimensão física mínima da célula, padrão `8`.
- `pet.outline.thickness_px`: espessura do contorno escuro fino.
- `pet.outline.double`: habilita o segundo filete claro/escuro.
- `pet.outline.dark` e `pet.outline.light`: cores dos dois filetes em RGB.
- `pet.outline.theme_auto`: lê apenas a preferência claro/escuro do tema de aplicativos do Windows para ordenar os filetes e escolher a placa.
- `pet.outline.plate_alpha`: opacidade da placa com formato elíptico sob o olho.

O preset `normal` mantém a textura ASCII perceptível sem preencher cada célula. `bold` aumenta a massa e `fine` reduz a densidade. A arte usa esclera azul-acinzentada clara (`#89969E`), íris azul-petróleo (`#3A6A82`), pupila escura (`#050C18`) e reflexos quase brancos (`#FFFFFA`); âmbar é acento. A diferença de luminância entre a pupila e a íris-base é 3,32:1, e entre o reflexo e a esclera é 3,03:1.

## Capturas e medidas

O script `scripts/legibility_lod_review.py` cria renders headless em 48, 64, 96, 128, 192 e 256 px, sobre preto, branco, cinza médio, azul escuro, xadrez com ruído e uma foto de teste. `docs/screenshots/legibility/lod_final/before/` e `after/` guardam cada fundo no tamanho nativo; os contatos `*_1x` não são ampliados e `*_ampliado_3x` são somente para inspeção. `comparacao/` apresenta os pares antes/depois.

`RELATORIO_CONTRASTE.md` reporta o percentil 5 do melhor dos dois filetes contra os pixels locais na borda, contraste interno pupila/íris, íris/esclera e reflexo/esclera, e as medianas renderizadas de pupila/fundo e íris/fundo. Pupila/íris e reflexo/esclera permanecem iguais em todos os fundos porque comparam cores fixas da paleta. A antiga leitura constante de 4,99:1 era apenas o contraste entre as cores da paleta anterior; não media contraste com o fundo. Agora a coluna separada pupila/fundo varia por fundo e escala.

Para regenerar as capturas atuais e a comparação com o conjunto histórico `before/` (preservado para não ser sobrescrito):

```powershell
.\.venv\Scripts\python.exe scripts\legibility_lod_review.py
```

O fundo de foto é um recurso de teste local. O aplicativo não captura nem analisa pixels da tela; no Windows, lê somente a preferência de tema claro/escuro.
