/** No-op: Sentry request-error capture has been removed. */
export const onRequestError = (
  _error: unknown,
  _request: unknown,
  _context: unknown
): void => {
  // intentionally empty
};

export const initializeObservability = async (): Promise<void> => {
  // intentionally empty — Axiom ships from the API; Better Stack is pull-based
};
