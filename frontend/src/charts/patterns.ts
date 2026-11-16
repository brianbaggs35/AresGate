/** How many textures there are: one for each of the eight hues, in the same order. */
export const TEXTURES = 8

/**
 * The texture of the `index`th series (from 0), as the number its CSS class and its `<pattern>`
 * carry (1 to 8), or null past the eighth, where everything is "other" and has none. The order is
 * fixed, so a texture goes with a hue on every chart: diagonal hatching, dots, cross-hatching,
 * the other diagonal, rules across, rules up, rings and a fine grid.
 *
 * A texture is drawn in forced-colors mode, in print and when the owner turns on *Use patterns*,
 * so no chart depends on color alone. A line has no area to hatch, so its texture is a dash.
 */
export function textureOf(index: number): number | null {
  return index < TEXTURES ? index + 1 : null
}

/** The class that gives a mark its fill texture (`fill: url(#chart-pattern-n)` when textures are
 * on), or undefined for a series that has none. */
export function textureClass(texture: number | null | undefined): string | undefined {
  return texture ? `chart-pat-${texture.toString()}` : undefined
}

/** The class that gives a line its dash when textures are on. */
export function dashClass(texture: number | null | undefined): string | undefined {
  return texture ? `chart-dash-${texture.toString()}` : undefined
}
