/*
 * Console-backed logger. Prefer Axiom (API) / platform logs for anything
 * that needs to make it off the box. Sentry has been removed.
 */

export const log = console;
