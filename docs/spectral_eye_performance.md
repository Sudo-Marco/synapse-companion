# Desempenho do olho espectral

Medição local do benchmark Qt (`800x450`, 10 segundos por fase, backend QPainter/CPU). O controle é o renderizador ASCII legado e o resultado é `pet.render_style: spectral`; ambos foram medidos no mesmo ambiente e com o mesmo script.

| Modo | Fase | ASCII legado | Espectral | Variação de CPU | FPS legado → espectral |
| --- | --- | ---: | ---: | ---: | ---: |
| ASCII | Ativo | 36,40% | 37,14% | +2,0% | 30,30 → 30,36 |
| ASCII | Repouso | 6,90% | 6,75% | −2,2% | 5,00 → 5,00 |
| HUD | Ativo | 37,18% | 38,59% | +3,8% | 30,29 → 30,37 |
| HUD | Repouso | 6,44% | 6,61% | +2,6% | 5,00 → 5,00 |

Os valores ficaram dentro da margem de 10% definida para CPU e mantiveram as metas de 30 FPS ativo e 5 FPS em repouso. Como o renderizador medido é QPainter, a VRAM não é usada nem contabilizada pelo benchmark.

Reprodução no Windows:

```powershell
python benchmarks/render_benchmark.py --seconds 10 --renderer ascii --render-style ascii --size 800x450 --output work/ascii_before.json
python benchmarks/render_benchmark.py --seconds 10 --renderer ascii --render-style spectral --size 800x450 --output work/spectral_after.json
```

É uma medição automatizada da janela Qt neste ambiente; não substitui uma avaliação visual manual em diferentes monitores, escalas de DPI ou papéis de parede.
