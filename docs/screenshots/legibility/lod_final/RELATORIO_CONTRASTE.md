# LOD ASCII — legibilidade por altura e fundo

As capturas são renders headless do próprio widget, compostos sobre fundos de teste. Cada arquivo `*_1x` mantém a resolução física indicada no nome; os arquivos `ampliado_3x` usam nearest-neighbor apenas para inspeção visual. A foto é um recurso local de teste e nenhuma tela do usuário é lida.

Silhueta é o percentil 5 do melhor contraste WCAG entre os dois filetes configurados (escuro e claro) contra cada pixel do fundo na borda geométrica fechada. Pupila/íris, íris/esclera e reflexo/esclera comparam as cores efetivas da paleta; por isso estes valores internos são iguais nos seis fundos. Pupila/fundo e íris/fundo usam pixels renderizados nas regiões do olho e variam conforme o fundo; valores baixos em fundos de luminância semelhante indicam mistura da cor preenchida, não perda da borda dupla.

O custo é a mediana de 3 medições do mesmo widget offscreen por quadro nos timers ativos (30 FPS) e em repouso (5 FPS). A linha anterior do mesmo benchmark foi 2,511 ms/quadro ativo e 2,727 ms/quadro em repouso.

| Altura | Fundo | Silhueta/fundo p05 | Pupila/íris | Íris/esclera | Pupila/fundo mediana | Íris/fundo mediana | Reflexo/esclera | Resultado |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 48 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 1.09:1 | 3.56:1 | 3.03:1 | PASSA |
| 48 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 19.32:1 | 5.89:1 | 3.03:1 | PASSA |
| 48 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 4.89:1 | 1.49:1 | 3.03:1 | PASSA |
| 48 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 1.09:1 | 3.1:1 | 3.03:1 | PASSA |
| 48 px | xadrez_ruido | 4.63:1 | 3.32:1 | 1.94:1 | 3.93:1 | 1.92:1 | 3.03:1 | PASSA |
| 48 px | foto_paisagem | 6.08:1 | 3.32:1 | 1.94:1 | 3.53:1 | 2.35:1 | 3.03:1 | PASSA |
| 64 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 1.08:1 | 3.56:1 | 3.03:1 | PASSA |
| 64 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 19.44:1 | 5.89:1 | 3.03:1 | PASSA |
| 64 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 4.92:1 | 1.49:1 | 3.03:1 | PASSA |
| 64 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 1.08:1 | 3.1:1 | 3.03:1 | PASSA |
| 64 px | xadrez_ruido | 4.61:1 | 3.32:1 | 1.94:1 | 4.38:1 | 1.86:1 | 3.03:1 | PASSA |
| 64 px | foto_paisagem | 6.29:1 | 3.32:1 | 1.94:1 | 4.31:1 | 2.23:1 | 3.03:1 | PASSA |
| 96 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 1.09:1 | 3.56:1 | 3.03:1 | PASSA |
| 96 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 19.3:1 | 5.89:1 | 3.03:1 | PASSA |
| 96 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 4.89:1 | 1.49:1 | 3.03:1 | PASSA |
| 96 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 1.08:1 | 3.1:1 | 3.03:1 | PASSA |
| 96 px | xadrez_ruido | 4.61:1 | 3.32:1 | 1.94:1 | 4.67:1 | 1.91:1 | 3.03:1 | PASSA |
| 96 px | foto_paisagem | 7.8:1 | 3.32:1 | 1.94:1 | 3.81:1 | 2.25:1 | 3.03:1 | PASSA |
| 128 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 3.76:1 | 3.61:1 | 3.03:1 | PASSA |
| 128 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 1.52:1 | 1.43:1 | 3.03:1 | PASSA |
| 128 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 2.04:1 | 1.49:1 | 3.03:1 | PASSA |
| 128 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 3.63:1 | 3.58:1 | 3.03:1 | PASSA |
| 128 px | xadrez_ruido | 4.59:1 | 3.32:1 | 1.94:1 | 2.13:1 | 1.62:1 | 3.03:1 | PASSA |
| 128 px | foto_paisagem | 8.51:1 | 3.32:1 | 1.94:1 | 2.39:1 | 2.39:1 | 3.03:1 | PASSA |
| 192 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 3.83:1 | 3.59:1 | 3.03:1 | PASSA |
| 192 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 1.49:1 | 1.43:1 | 3.03:1 | PASSA |
| 192 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 1.93:1 | 1.49:1 | 3.03:1 | PASSA |
| 192 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 3.74:1 | 3.57:1 | 3.03:1 | PASSA |
| 192 px | xadrez_ruido | 4.6:1 | 3.32:1 | 1.94:1 | 2.13:1 | 1.58:1 | 3.03:1 | PASSA |
| 192 px | foto_paisagem | 8.58:1 | 3.32:1 | 1.94:1 | 2.57:1 | 2.23:1 | 3.03:1 | PASSA |
| 256 px | preto | 20.43:1 | 3.32:1 | 1.94:1 | 3.73:1 | 3.61:1 | 3.03:1 | PASSA |
| 256 px | branco | 19.46:1 | 3.32:1 | 1.94:1 | 1.5:1 | 1.43:1 | 3.03:1 | PASSA |
| 256 px | cinza_medio | 4.93:1 | 3.32:1 | 1.94:1 | 1.95:1 | 1.48:1 | 3.03:1 | PASSA |
| 256 px | azul_escuro | 17.77:1 | 3.32:1 | 1.94:1 | 3.68:1 | 3.58:1 | 3.03:1 | PASSA |
| 256 px | xadrez_ruido | 4.59:1 | 3.32:1 | 1.94:1 | 1.96:1 | 1.59:1 | 3.03:1 | PASSA |
| 256 px | foto_paisagem | 8.51:1 | 3.32:1 | 1.94:1 | 2.54:1 | 2.12:1 | 3.03:1 | PASSA |

## Desempenho

| Fase | Linha anterior (ms/quadro) | Atual (ms/quadro) | Delta | FPS medido | Dentro de 10% |
|---|---:|---:|---:|---:|---|
| Ativo | 2,511 | 2.654 | +5.7% | 30.0 | SIM |
| Repouso | 2,727 | 2.644 | -3.0% | 5.0 | SIM |
