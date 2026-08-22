/**
 * What can go wrong talking to the job API, as distinct types.
 *
 * One error carrying a status code would push the same `if (status === 404)`
 * into every call site. These are separate because callers act on them
 * differently: a stale cursor means start the listing over, a missing job means
 * render not-found, a rejected filter means the request was built wrong.
 */

/** Base type, so a caller that treats every failure alike still can. */
export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

/** The API could not be reached, or the response was not JSON. */
export class ApiUnreachableError extends ApiError {
  constructor(readonly cause?: unknown) {
    super("The job service could not be reached.");
  }
}

/** The cursor no longer describes a position. Start the listing again. */
export class StaleCursorError extends ApiError {
  constructor() {
    super("This page of results has expired. Reload the listing.");
  }
}

/** No job has that identifier. */
export class JobNotFoundError extends ApiError {
  constructor(readonly jobId: string) {
    super("That job could not be found.");
  }
}

/** The request was rejected as malformed, which means this client built it wrong. */
export class InvalidRequestError extends ApiError {
  constructor(readonly detail: string) {
    super(`The job service rejected the request: ${detail}`);
  }
}

/** The API answered, but with something this client does not handle. */
export class UnexpectedResponseError extends ApiError {
  constructor(readonly status: number) {
    super(`The job service responded unexpectedly (${status}).`);
  }
}
