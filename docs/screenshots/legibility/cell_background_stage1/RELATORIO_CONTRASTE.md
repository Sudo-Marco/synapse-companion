# Protótipo offline — fundo de cor por célula

Esta é uma prova visual isolada da técnica proposta. O renderizador do app, a paleta ativa e qualquer outro subsistema não foram alterados. Cada tile mantém o tamanho físico indicado; `contato_ampliado_3x.png` é ampliado por nearest-neighbor apenas para inspeção.

## Métricas de contraste e restrições

As razões WCAG são calculadas entre luminâncias relativas. `pupila/fundo` compara a pupila escura com o fundo de teste diretamente atrás dela; `reflexo/esclera` compara branco puro com #EEF4F1. Esses dois pares podem revelar incompatibilidade entre a paleta especificada e a meta universal >=3:1.

| Altura | Fundo | Silhueta/fundo p05 | Pupila/íris | Íris/esclera | Pupila/fundo mediana | Reflexo/esclera | Pupila (cél.) | Reflexo máx. (cél.) | Anel (cél.) | Anel fechado | Contorno fechado |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| 48 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 48 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 48 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 48 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 48 | xadrez_ruido | 3.10:1 | 3.09:1 | 2.86:1 | 4.60:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 48 | foto | 4.31:1 | 3.09:1 | 2.86:1 | 1.61:1 | 1.11:1 | 3×4 | 1×1 | 6 | não | sim |
| 64 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 64 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 64 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 64 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 64 | xadrez_ruido | 3.11:1 | 3.09:1 | 2.86:1 | 4.78:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 64 | foto | 4.19:1 | 3.09:1 | 2.86:1 | 1.63:1 | 1.11:1 | 3×4 | 1×1 | 18 | sim | sim |
| 96 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 96 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 96 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 96 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 96 | xadrez_ruido | 3.10:1 | 3.09:1 | 2.86:1 | 4.52:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 96 | foto | 4.28:1 | 3.09:1 | 2.86:1 | 1.64:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | xadrez_ruido | 3.10:1 | 3.09:1 | 2.86:1 | 4.62:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 128 | foto | 4.23:1 | 3.09:1 | 2.86:1 | 1.64:1 | 1.11:1 | 3×4 | 2×2 | 18 | sim | sim |
| 192 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 192 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 192 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 192 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 192 | xadrez_ruido | 3.10:1 | 3.09:1 | 2.86:1 | 4.79:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 192 | foto | 4.26:1 | 3.09:1 | 2.86:1 | 1.67:1 | 1.11:1 | 5×4 | 2×2 | 22 | sim | sim |
| 256 | preto | 9.58:1 | 3.09:1 | 2.86:1 | 1.18:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |
| 256 | branco | 13.89:1 | 3.09:1 | 2.86:1 | 17.74:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |
| 256 | cinza_medio | 3.52:1 | 3.09:1 | 2.86:1 | 4.49:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |
| 256 | azul_escuro | 8.80:1 | 3.09:1 | 2.86:1 | 1.03:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |
| 256 | xadrez_ruido | 3.11:1 | 3.09:1 | 2.86:1 | 4.77:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |
| 256 | foto | 4.24:1 | 3.09:1 | 2.86:1 | 1.69:1 | 1.11:1 | 6×6 | 2×2 | 28 | sim | sim |

## Leitura do resultado

Mínimos observados: silhueta/fundo 3.10:1; pupila/íris 3.09:1; íris/esclera 2.86:1; pupila/fundo 1.03:1; reflexo/esclera 1.11:1.

A meta de 3:1 para **pupila/fundo** não pode ser satisfeita em todos os fundos com a pupila #0A1A22: sobre preto, duas cores quase pretas têm contraste próximo de 1:1. A meta de 3:1 para **reflexo/esclera** também conflita com reflexo #FFFFFF e esclera #EEF4F1; a razão física entre essas cores é cerca de 1.11:1. Além disso, íris interior #2E9DB3 contra esclera #EEF4F1 fica em 2.86:1. A silhueta passa 3:1, mas esses pares da paleta não. Para preservar as cores pedidas, as metas devem medir pupila/íris e reflexo/íris ou aceitar valores abaixo de 3:1 nesses pares.

Restrições de células: pupila >=3×3, reflexo principal >=2×2, anel de íris fechado de uma célula e contorno externo fechado. A grade de 48 px tem apenas 6 linhas de 8 px; em 48 e 64 px não foi possível encaixar o reflexo 2×2 na íris sem invadir a pupila. Esses tamanhos falham a restrição do reflexo. Reduzir a célula mínima ou usar uma exceção de baixa resolução seria necessário, contrariando o mínimo uniforme de 8 px.

Este relatório é um render de protótipo offline. NÃO validado no aplicativo nem em desktop real. Nenhum teste pytest foi adicionado/alterado nesta etapa.
