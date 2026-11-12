# Sprite sheet do Piu

O pet flutuante usa `pet_spritesheet.png` e `pet_atlas.json`. O PNG tem fundo
transparente e mede 384 × 1296 px: 8 colunas × 27 linhas, com quadros de 48 × 48.

## Formato do atlas

O JSON declara largura e altura do quadro, número de colunas e linhas, nome do
PNG, ponto de âncora e as animações. Cada animação informa:

- `row`: linha na grade, começando em zero;
- `frames`: quantidade de quadros usados a partir da primeira coluna;
- `fps`: quadros por segundo;
- `loop`: se a animação reinicia ao chegar ao último quadro.

O quadro `i` de uma animação começa em `x = i × 48`, `y = row × 48`. A âncora
`(24, 43)` fica nos pés do pintinho; o renderizador a alinha à posição do pet.
Ao ampliar, a imagem é recortada diretamente do PNG com filtro de vizinho mais
próximo. A escala usa passos de 0,5 para manter os pixels nítidos.

As animações terminadas em `_left` já estão espelhadas no próprio atlas. O
renderizador seleciona essas linhas quando o movimento lateral aponta para a
esquerda; não espelha esses quadros de novo.

## Ajustes no projeto

`sprite_mapping.json` é o único arquivo de ligação entre emoções/ações já
existentes no Synapse Pet e os nomes das animações. Ele pode ser editado sem
alterar o adaptador. A escala do pet flutuante fica em `pet.sprite_scale` no
`configs/default.yaml`; o padrão `4` produz um quadro de 192 × 192 px.

`pet_demo.html` do pacote recebido serviu apenas como referência e não é
carregado nem executado pelo aplicativo. As animações são escolhidas pela
camada Python usando os estados e movimentos que o projeto já publica.
