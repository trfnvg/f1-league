# «Огни погасли»: панорамы Яс-Марины

Каталог: `league/static/league/images/lights-out/`. Два самостоятельных ракурса, один и тот же подход к свету и движению. Игра загружает один WebP подходящего размера через `picture`.

| Ракурс | Оригинал для веба | Версия повышенного разрешения |
| --- | --- | --- |
| Широкий | `grid-wide.webp` (1672 × 941) | `grid-wide-hd.webp` (3840 × 2160) |
| Портретный | `grid-portrait.webp` (941 × 1672) | `grid-portrait-hd.webp` (1440 × 2560) |

`grid-cover.webp` — отдельное превью 640 × 360 для каталога. Исходная графика создана встроенным ImageGen; HD-версии экспортированы с офлайн-суперразрешением (subpixel CNN), не генерируются во время игры.

## Промпты для панорам

Общий промпт:

> Use case: photorealistic-natural. Project asset: entirely new photoreal cinematic front-row F1 driver-eye still at Yas Marina Abu Dhabi, one coherent exposure with razor sharp authentic detail. View straight down start finish straight, symmetrical vanishing point around x=.50, y=.51. Lower quarter shows black satin carbon fibre open-wheel cockpit, recognizable front tyres, gloved hands and steering wheel seen from driver view. Left: packed multi-tier main grandstand under iconic white canopy, distinct tiny spectators, absolutely NO FLAGS, poles with cloth, or banners. Right: open garage bays with helmeted team mechanics and trolley tyres, separated from racing surface by a clearly visible continuous low concrete pit wall topped by metal wire safety fencing receding to vanishing point; mechanics behind this fence, never on circuit. Soft apricot dusk, silver-blue ambient shadows, cool electric strip lights in garages and grandstand, tiny warm practical lights. Leave upper middle sky reasonably open for real interactive lights overlay; no traffic lights, no digital panels, no HUD, absolutely no baked solar disc or lens flare (we animate the sun), no lettering or watermark. Extraordinary tactile surfaces, grounded natural human proportions.

Окончание для ПК: “Native high resolution 3840x2160 16:9 landscape desktop matte.”

Окончание для телефона: “Native high resolution 2160x3840 9:16 vertical phone composition, wide angle shows both grandstand AND nearby garages and fence inside portrait, steering wheel falls near bottom.”

При замене ракурса заново привязать области людей в `lights-out-scene.js` и зоны неба и освещения в `lights-out.css`. Анимация использует пиксели самой панорамы. Ночная экспозиция применяется только к сцене, не к игровому светофору.
