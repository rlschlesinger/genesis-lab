// The CSS tokens (tokens.css) for code that draws with JavaScript (charts, the plate), so
// colours are still defined in exactly one place.

export type TokenName =
  | "--violet" | "--violet-deep" | "--safranin" | "--iodine" | "--stain-ink"
  | "--stain-ink-soft" | "--graticule" | "--graticule-strong" | "--field" | "--font";

export function token(name: TokenName, element: Element = document.documentElement): string {
  return getComputedStyle(element).getPropertyValue(name).trim();
}
