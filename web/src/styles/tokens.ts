// The CSS tokens (tokens.css) for code that draws with JavaScript (charts, the plate), so
// colours are still defined in exactly one place.

export type TokenName =
  | "--violet" | "--violet-deep" | "--safranin" | "--iodine" | "--stain-ink"
  | "--stain-ink-soft" | "--graticule" | "--graticule-strong" | "--field" | "--font"
  | "--size-small" | "--chart-height" | "--chart-axis" | "--prey" | "--predator"
  | "--selected" | "--food-a" | "--food-b";

export function token(name: TokenName, element: Element = document.documentElement): string {
  return getComputedStyle(element).getPropertyValue(name).trim();
}

/** A length token ("0.8rem", "12px") in pixels, for drawing on a canvas, which can't use CSS
 *  units. ``rootPx`` is the root font size (what 1rem is). Anything else is a mistake in
 *  tokens.css, so it throws rather than draw at a made-up size. */
export function toPixels(value: string, rootPx: number): number {
  const match = /^(-?[\d.]+)(rem|px)$/.exec(value.trim());
  if (!match) throw new Error(`not a length in rem or px: ${JSON.stringify(value)}`);
  const n = Number(match[1]);
  return match[2] === "rem" ? n * rootPx : n;
}

export function tokenPx(name: TokenName, element: Element = document.documentElement): number {
  const rootPx = Number.parseFloat(getComputedStyle(document.documentElement).fontSize);
  return toPixels(token(name, element), rootPx);
}
