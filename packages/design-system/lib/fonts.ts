// Brand fonts (/specs/brand.md): Plus Jakarta Sans for headings,
// Satoshi for body, Menlo for code. `next/font/google` is a Next.js
// runtime API and must be invoked from the consuming app, so each
// Next app sets up its own font instances and forwards the variable
// classNames to the <html> element. This module just exposes the
// shared tail of utility classes (touch + antialiasing) so both apps
// stay in lockstep.

import { cn } from '@repo/design-system/lib/utils';

/** Combine the per-app font variable classNames with the shared
 * brand-required utilities. Pass the result to `<html className=...>`. */
export const brandFontShell = (...variables: string[]) =>
  cn(...variables, 'touch-manipulation font-sans antialiased');

/** Backwards-compatible alias used by older next-forge layouts. The
 * admin / candidate root layouts now build the className via
 * `brandFontShell` directly so they can name their own font instances. */
export const fonts = 'touch-manipulation font-sans antialiased';
