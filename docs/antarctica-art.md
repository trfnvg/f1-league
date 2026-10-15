# Antarctica game assets

Generated with the built-in GPT image generation tool on 2026-10-15.
Original PNG resolution and console transparency are preserved.

## Background

Asset: `league/static/league/images/doodle-jump/antarctica-canyon-v1.png`

Prompt:

> Use case: stylized-concept. Production game background for a retro 16-bit Formula 1 cowboy vertical jumping game. Antarctica glacial canyon, enormous layered ice cliffs only at left and right margins, distant snowy Antarctic mountains and soft polar mist through the open central corridor. Restrained desaturated steel blue, navy ice shadows, pale cyan snow, faint violet polar sky. Beautiful detailed crisp pixel art, readable clustered pixels, no blur, no painterly brushwork. Portrait vertical composition. No floor at bottom, no horizon line cutting the image, continuous ice canyon going vertically beyond top and bottom, suitable for scrolling upwards with crossfade repeat. Center 50 percent quiet with low contrast to keep tiny characters and platforms readable. No people, no text, no HUD, no platforms, no logos, no screenshot frame. Full bleed background art only.

## Control console

Asset: `league/static/league/images/doodle-jump/f1-control-console-v1.png`

Prompt (transparent background enabled):

> Use case: stylized-concept. Production sprite for 16-bit retro Formula 1 platform game. ONE standalone Formula 1 race car control console on a sturdy steel pedestal, front view with very slight view of upper surface. A wide dark graphite telemetry monitor showing simple mint green outline diagram of a Formula 1 car, beside it a HUGE raised round RED PUSH BUTTON occupying the right third of the console top, chrome rim. Exposed cables and tiny amber indicators. Readable simple silhouette at small in-game size, detailed crisp pixel art, chunky pixel clusters, dark outlines, vintage industrial garage mood. Entire console visible, centered, generous transparent padding. Real transparent background. No characters, no floor, no shadows outside sprite, no scene, no text, no multiple views. The large red button must be very obvious.

## Integration

The scene begins once per run at 8000 points after entering the forgotten paddock.
Physics pauses during the 8.4-second scene. The existing hero and Toto sprites
are animated through arrival, shove, button press and portal capture.
The Antarctica background scrolls downward with ascent and blends upright tiles
without allocating a full-size offscreen background canvas. Snow and ice
platforms are drawn in Canvas. Existing platform collision dimensions remain.
The administrator preview uses the unranked test-run guards.

Validation: native Canvas rendering at mobile and desktop dimensions, including
resizes during all scene phases; score preservation, threshold and once-only
transition, safe landing, restart cleanup, and no score/attempt writes in preview.
An actual iPhone/Safari session was not available for verification.
