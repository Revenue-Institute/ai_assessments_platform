/*
 * Console-backed logger. The observability stack ships Sentry +
 * Axiom only (spec §15); @logtail/next was a next-forge inherited
 * dep that never shipped in v1, so this re-export aliases the
 * standard console so callers can keep using `import { log }`.
 *
 * Prefer Sentry breadcrumbs / spans for anything that needs to
 * make it off the box.
 */

export const log = console;
