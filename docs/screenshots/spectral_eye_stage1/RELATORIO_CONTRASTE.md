# Etapa 1 — olho espectral (protótipo offline)

Prévia vetorial com brilho em camadas, sombra, íris, pupila, reflexos grandes, runas e fiapos. Não foi integrada ao app; não houve leitura da tela nem captura de pixels do desktop.

| Medida | Mínimo observado | Meta | Resultado |
|---|---:|---:|---|
| Silhueta contra o fundo (pior ponto amostrado) | 3.62:1 | ≥ 3:1 | PASSA |
| Pupila contra íris | 4.66:1 | ≥ 3:1 | PASSA |
| Reflexo branco contra esclera translúcida | 1.05:1 | ≥ 3:1 | FALHA |

A razão reflexo/esclera falha sobretudo no fundo branco: a esclera `#DFFBFF` com 20% de opacidade fica quase branca sobre branco. Isso é uma incompatibilidade entre o valor de contraste ≥3:1 e a esclera clara/translúcida pedida. O valor foi medido sem reinterpretar a métrica; a Etapa 2 não começou.

A silhueta é calculada como a melhor separação local entre o fundo e uma das três bandas visíveis (sombra suave, filete escuro ou núcleo luminoso), amostrando 256 pontos na borda. Pupila/íris usa as cores sólidas renderizadas. Reflexo/esclera compara o glint branco à cor da esclera translúcida composta sobre cada fundo. Dormindo: pupila/íris e reflexo/esclera são N/A porque o olho fechado não os desenha.

| Fundo | Silhueta mínima | Pupila/íris | Reflexo/esclera |
|---|---:|---:|---:|
| preto | 16.18:1 | 4.66:1 | 12.99:1 |
| branco | 13.39:1 | 4.66:1 | 1.05:1 |
| cinza | 3.95:1 | 4.66:1 | 2.90:1 |
| azul escuro | 14.56:1 | 4.66:1 | 10.51:1 |
| xadrez ruido | 4.55:1 | 4.66:1 | 1.48:1 |
| foto | 3.62:1 | 4.66:1 | 2.47:1 |

## Cobertura

108 combinações: seis fundos × seis alturas (48, 64, 96, 128, 192 e 256 px) × três estados (neutro, feliz, dormindo). O olho mantém proporção 2:1; abaixo de 96 px o anel e a fumaça são reduzidos.

## Medidas geométricas

| Altura | Íris / altura | Pupila / altura | Reflexo grande / altura | Runas |
|---:|---:|---:|---:|---:|
| 48 px | 60% | 27% | 13% | 6 |
| 64 px | 60% | 27% | 13% | 6 |
| 96 px | 60% | 27% | 13% | 10 |
| 128 px | 60% | 27% | 13% | 10 |
| 192 px | 60% | 27% | 13% | 12 |
| 256 px | 60% | 27% | 13% | 12 |

Mínimos pedidos: íris ~60%, pupila ≥20%, reflexo principal ≥10% da altura. Contorno contínuo foi desenhado por QPainter com antialiasing. As capturas são avaliações visuais offline, não teste automatizado de integração.

A foto é `Lake Mountain Landscape.jpg`, de Bonnie Moreland, CC0 1.0, usada anteriormente como fundo local de renderização no próprio repositório. Não vem da tela do usuário.

As medições completas por fundo/estado/altura estão em `contraste.csv`.
