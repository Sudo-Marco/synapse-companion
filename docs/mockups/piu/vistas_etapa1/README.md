# Novas vistas e movimentos do Piu — Etapa 1

Estas folhas são mockups offline para aprovação visual. Elas usam a paleta e a linguagem do Piu aprovado em `../`, e reutilizam o sprite de perfil aprovado no quadro de perfil/idle. Nenhum código do app, da SNN ou do motor de movimento foi alterado nesta etapa.

## Folhas

| Arquivos | Conteúdo |
|---|---|
| `frente_1x.png`, `frente_4x.png` | Idle, piscar, feliz, cantar, susto, dormir, post-it e olhar para cima/voo. |
| `costas_1x.png`, `costas_4x.png` | Idle, balanço de cauda, topete ao vento e olhar por cima do ombro. |
| `corrida_lateral_1x.png`, `corrida_lateral_4x.png` | Oito fases de corrida de perfil, com alternância dos pés, movimento das asas e poeira. |
| `pulo_1x.png`, `pulo_4x.png` | Antecipação em dois quadros, impulso, subida, ápice, descida, pouso em dois quadros e recuperação; sombra encolhe e clareia no ar. |
| `corrida_para_fundo_*.png`, `volta_para_camera_*.png` | Seis quadros por direção, com níveis nativos 32/24/16 px no afastamento e retorno. |
| `virada_vistas_1x.png`, `virada_vistas_4x.png` | Perfil, duas transições 3/4, frente, duas transições para costas e costas. |
| `corrida_bilateral_1x.png`, `corrida_bilateral_4x.png` | Comparação do ciclo correndo para a direita e espelhado para a esquerda, com reflexo corporal corrigido para manter a luz global no alto à esquerda. |
| `niveis_profundidade_1x.png`, `niveis_profundidade_4x.png` | Perfil/frente/costas em idle/corrida nos três tamanhos nativos. |
| `inventario_frames.json` | Rótulos, duração de prévia, pivôs comuns e caixas de hitbox medidas por quadro. |

As pranchas 1x mantêm os pixels nativos; 4x usa vizinho mais próximo. Os desenhos 32, 24 e 16 px são rasterizados diretamente em cada resolução. O pivô comum é `(16, 40)` no canvas 32x44; poses aéreas mantêm esse ponto virtual de apoio. A revisão bilateral preserva o desenho espelhado e recoloca o brilho do corpo no alto à esquerda; a implementação final deve manter essa correção como camada ou passo de composição.

Para a vista traseira, o olho está naturalmente oculto. Nos quadros de frente, perfil e 3/4, o olho continua escuro com reflexo branco; no sprite nativo de 16 px a área do olho mantém pelo menos 2x2 pixels e um ponto de reflexo.

## Limites desta entrega

Os ciclos e distâncias são propostas visuais para aprovação, não uma implementação integrada nem uma medição de foot sliding. Hitboxes e durações são prévias aproximadas para orientar a Etapa 2. Não houve teste da GUI no desktop real.
