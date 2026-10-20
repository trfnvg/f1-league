# Summit platforms and falling objects

The final biome now uses the regular 108–146 unit platform gap, roughly 58–61
unit ordinary footholds, side alternatives every third main foothold, and a
compact spring. Cable cars, purple chains, goats and fragile platforms remain.
Side footholds are lower than the main route, so they never change its anchor.
Ferrari drones remain stompable during retreat and fall as wrecks after impact.

Existing tire/cone artwork is reused for falling objects: spawn above the view,
100–135 units/second, 720 unit spacing, at most three active. Generation retains
existing objects; tires bounce, cones retain their harmful contour collision.

Artwork: built-in image generation, project asset
`league/static/league/images/doodle-jump/summit-platforms-v1.png`.
Four vertical cells are repacked and trimmed once on stage load. Runtime uses
the existing raster cache. The asset is lazy-loaded with the summit, preserving
the initial download. No original sprite resolution was reduced.

Generation prompt:

> Use case: stylized-concept. Asset type: production 2D pixel art sprite sheet for retro Formula 1 alpine paddock jumping game. Generate FOUR isolated horizontal landing platforms arranged in ONE VERTICAL COLUMN, each centered in an equal quarter of the image, generous empty transparent gutters. Each platform exactly same proportions about 5:1 width to height, straight horizontal flat top, straight-on side view with a little visible top surface, no perspective skew. Platform 1: beautiful dark blue-grey mountain pit-lane service gantry, brushed steel, small gold brackets, ivory top edge, restrained red end markers. Platform 2: matching moving platform with copper mechanical end brackets. Platform 3: matching breakable platform with readable cracks through its steel/stone structure, warmer rust underside. Platform 4: matching spring platform with compact central brass coil spring and narrow flat landing cap, no stretching. Premium handcrafted 16-bit pixel art, crisp intentional pixel clusters, detailed but readable at 65 pixels wide. Cool slate, muted ivory, subtle teal, small amber highlights. No snow overload, no glowing neon, no text, no UI, no background, no shadows outside sprites. Authentic alpha transparent background. Four equally separated complete platform sprites in one vertical column; do not draw any other objects.

Cutout refinement prompt:

> Remove ALL dark fog, glow, gradient, shadow and colored haze around these four platform sprites. Preserve only hard opaque pixels inside the actual metallic platform outlines. Everywhere outside physical objects must be 100% transparent alpha 0. Keep all four platforms exactly in their existing positions, separate rows, preserve their design and crisp pixel art. No background, no glow, no soft shadow. This is a production spritesheet needing precise cutouts.

Validation: native Canvas suite in mobile and desktop dimensions, including
retreating drone stomp, lazy platform artwork, main-route gaps, side alternatives,
offscreen hazard spawn, retained objects and biome/boss regressions. PNG previews
rendered from the game for visual inspection.
