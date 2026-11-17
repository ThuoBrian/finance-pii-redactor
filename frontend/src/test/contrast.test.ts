// Every colour pair that carries text, or marks the edge of a control, must
// stay above WCAG AA in both themes. Reads the tokens straight from
// index.css, so a later palette tweak cannot quietly break contrast.
import { describe, expect, it } from "vitest";

import css from "../index.css?raw";

function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
    out[m[1]!] = m[2]!.toLowerCase();
  }
  return out;
}

const lightBlock = css.slice(css.indexOf(":root {"), css.indexOf("@media (prefers-color-scheme: dark)"));
const darkBlock = css.slice(
  css.indexOf("@media (prefers-color-scheme: dark)"),
  css.indexOf("@theme inline"),
);
const light = { white: "#ffffff", ...tokens(lightBlock) };
// Dark mode overrides only some tokens; the rest carry over from light.
const dark = { ...light, ...tokens(darkBlock) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// [foreground, background, minimum]
const TEXT = 4.5;
const EDGE = 3;
const PAIRS: [string, string, number][] = [
  ...["bg", "card", "surface", "surface-2"].flatMap((bg): [string, string, number][] => [
    ["text", bg, TEXT],
    ["muted", bg, TEXT],
  ]),
  ["link", "card", TEXT],
  ["link", "primary-soft", TEXT], // info badge
  ["text", "primary-soft", TEXT], // selected review row
  ["muted", "primary-soft", TEXT],
  ["white", "primary", TEXT], // primary button
  ["white", "primary-hover", TEXT],
  ["white", "danger-solid", TEXT], // danger button
  ["danger", "card", TEXT],
  ["danger", "danger-soft", TEXT],
  ["warn", "card", TEXT],
  ["warn", "warn-soft", TEXT],
  ["success", "card", TEXT],
  ["success", "success-soft", TEXT],
  ["text", "danger-soft", TEXT], // notices
  ["text", "warn-soft", TEXT],
  ["text", "success-soft", TEXT],
  ["border", "card", EDGE], // inputs and selects
  ["border", "bg", EDGE],
  ["ring", "card", EDGE], // focus ring
  ["ring", "bg", EDGE],
];

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme contrast", (_name, theme: Record<string, string>) => {
  it.each(PAIRS)("%s on %s", (fg, bg, min) => {
    expect(theme[fg], `missing token --${fg}`).toBeDefined();
    expect(theme[bg], `missing token --${bg}`).toBeDefined();
    expect(contrast(theme[fg]!, theme[bg]!)).toBeGreaterThanOrEqual(min);
  });
});
