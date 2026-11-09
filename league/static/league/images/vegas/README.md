# Vegas Pit — visual assets v2

`meme-symbols-v2.png` is a new 1254 × 1254 RGBA sprite atlas generated using
the built-in image-generation tool, not a collage of earlier arcade sprites.
The selected PNG is stored here in the project; the runtime does not depend on
the generator's output folder. No command-line API fallback was used.

`strip-v2.svg` is the code-native background illustration. The metallic cabinet,
buttons and transitions are drawn in `league/static/league/vegas.css`; lightning
and flames are bounded, transient canvas effects in `vegas.js`.

## Atlas mapping

| Row | Column 1 | Column 2 | Column 3 |
| --- | --- | --- | --- |
| 1 | `tyre`: Bono, my tyres! | `duck`: GP2 Engine | `banana`: Sbinalla |
| 2 | `berry`: Smooth Operator | `russell`: T-Pose Russell | `toto`: No, Michael, no! |
| 3 | `bath`: El Plan | `wild`: Safety Duck | `scatter`: Vegas Crown |

Internal keys and payout weights are unchanged. CSS uses a 3×3 background atlas;
no raster cropping pipeline or runtime download from a third-party art service.

## Generation prompt (verbatim)

```text
Use case: stylized-concept. Asset: production game sprite atlas for a premium humorous Formula One themed Las Vegas slot, nine ORIGINAL icons in one perfectly aligned 3 by 3 grid on a TRULY TRANSPARENT background. Square canvas. Each of the nine equal square cells has exactly one isolated fully visible icon, centered with generous transparent padding, no icon crosses cell borders, consistent apparent size and straight-on view. No visible grid, no frames, no captions, no typography, no watermark. A cohesive premium playful 3D illustration style: sculpted rounded forms, rich enamel colors, tactile chrome and gold details, beautiful controlled highlights, polished game collectible renders, crisp readable silhouettes even at 64 pixels. NOT pixel art, NOT photographic collages. All nine icons belong to the same art direction and studio lighting, no backgrounds or floor shadows. Strict reading order: TOP LEFT a comically exhausted slick racing tire with eyebrows and a sweaty face, waving a tiny white surrender flag, humorous 'my tyres are gone' idea. TOP CENTER an absurd small red racing engine with a tiny propeller and one harmless little smoke puff, underpowered engine meme. TOP RIGHT a shiny red racing helmet mounted on a spinning toy top, stylish red curved motion ribbon around it, spinning-car meme. MIDDLE LEFT a handsome smiling dark-haired racing driver bust with aviator sunglasses and a vintage microphone, red racing collar, smooth operator meme. MIDDLE CENTER a charming brown-haired racing driver miniature in white and pale-blue racing suit, standing in a clear full-body T-pose with arms outstretched, amused expression. MIDDLE RIGHT a comically furious dark-haired team principal bust with black headset, shouting at a red telephone, tiny stylized lightning sparks, no text. BOTTOM LEFT a cunning bearded veteran racing driver in emerald green riding a miniature golden chess knight while holding a rolled blueprint, 'the plan' meme. BOTTOM CENTER a cute golden rubber duck shaped like a sleek safety car, four little dark wheels and amber roof beacon, premium teal accents, clearly readable duck silhouette. BOTTOM RIGHT a dazzling Las Vegas racing helmet wearing a small diamond crown, magenta visor, gold shell and two discrete small casino chips at its base, jackpot scatter icon. All icons detailed and humorous, with natural non-grotesque faces. No official logos. Again: exactly nine icons in a REGULAR 3x3 atlas, identical square cells and wide transparent gutters, no text anywhere, true alpha transparency.
```
