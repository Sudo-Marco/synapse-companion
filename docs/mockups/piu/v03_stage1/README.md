# Piu 0.3 — revisão visual, Etapa 1

Estas folhas registram a revisão visual aprovada da arte do Piu 0.3. Os PNGs
individuais em `sprites/` são as fontes editáveis; a integração do atlas e dos
metadados de runtime fica em `src/synapse_pet/assets/pixel/animations.json`.

## Folhas do personagem

- `vistas_lod_1x.png` e `vistas_lod_4x.png`: perfil, frente e costas nos LODs
  nativos perto 48×48, médio 32×32 e longe 20×20. Cada tamanho é desenhado
  diretamente na sua própria grade; a folha 4× usa vizinho mais próximo.
- `poses_novas_1x.png` e `poses_novas_4x.png`: pensando, cansado,
  descansando, ouvindo, três balanços, quatro pulinhos, três cabeceios,
  pego no alto, queda/pancada e espiando pela borda.
- `inventario_v03_stage1.json`: tamanhos nativos, pivô proposto, caixas de
  hitbox e divisão dos ciclos de dança. É um inventário visual, não um formato
  de runtime.
- `sprites/`: PNGs individuais com transparência, nomeados por vista, LOD,
  ação e fase. O empacotador usa essas imagens sem redimensioná-las.

As vistas traseiras usam nuca clara, asas dobradas com pontas destacadas e
cauda em leque de três penas. O marrom escuro fica no limite externo e em
linhas curtas; as rampas de amarelo, asa e bico têm quatro tons. A silhueta
inclui topete separado, peito com pequenas marcas, olho com dois reflexos,
bochechas, linha da boca e pés com três dedos. O filete claro externo é
opcional e serve de halo para fundos escuros.

## Legibilidade

- `legibilidade_2x.png`, `legibilidade_3x.png` e `legibilidade_4x.png` mostram
  cada vista e cada LOD nos fundos preto, branco, cinza, azul escuro, xadrez
  com ruído e fotografia.
- `contraste_legibilidade.csv` resume a razão mínima e média para cada fundo.
  A medida compara a melhor das duas cores adjacentes do contorno (marrom
  externo e creme claro) com amostras locais do fundo sob o halo pareado. É uma
  medida de legibilidade do contorno duplo, não afirma que uma cor isolada
  tenha contraste suficiente em todo fundo.

| Fundo | Mínimo do contorno pareado | Critério |
|---|---:|---|
| Preto | 17,84:1 | passa ≥ 3:1 |
| Branco | 11,94:1 | passa ≥ 3:1 |
| Cinza médio | 3,49:1 | passa ≥ 3:1 |
| Azul escuro | 13,21:1 | passa ≥ 3:1 |
| Xadrez com ruído | 3,27:1 | passa ≥ 3:1 |
| Foto | 3,26:1 | passa ≥ 3:1 |

Os valores são medidos sobre fundos estáticos de mockup. O fundo fotográfico é
a amostra CC0 documentada em [`../README.md`](../README.md). Isso não captura
nem lê a tela do usuário.

## Cenários por horário

- `ambientes_5_periodos_1x.png` e `ambientes_5_periodos_3x.png` comparam
  madrugada, manhã, tarde, entardecer e noite.
- `ambiente_<periodo>_1x.png` e `ambiente_<periodo>_3x.png` são os arquivos
  individuais de cada cena. As ampliações usam vizinho mais próximo.
- Cada cena mede 640×240 px e inclui um Piu nativo de 48 px (20% da altura),
  céu em faixas, três planos de colinas, nuvens, sol ou lua, árvore, casa,
  cerca, riacho com reflexos e flores. O céu recebe pontilhado sutil; os
  elementos do personagem e do primeiro plano ficam lisos.

## Regenerar as folhas

Com o ambiente virtual do projeto ativo:

```powershell
.\.venv\Scripts\python.exe docs\mockups\piu\v03_stage1\generate_mockups.py
```

Este gerador depende de Pillow e NumPy, já usados pelo projeto. Para atualizar
os atlases de runtime depois de editar os PNGs, execute também:

```powershell
.\.venv\Scripts\python.exe tools\build_piu_assets.py
```
