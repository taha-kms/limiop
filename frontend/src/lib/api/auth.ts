/**
 * Registering, signing in, and signing out.
 *
 * Every call goes to this application's own `/api/auth/*` routes rather than to
 * the API directly, so the session cookie is stored same-origin and stays
 * HttpOnly. Nothing here ever sees the token.
 */

export class AuthUnavailableError extends Error {
  constructor() {
    super("The account service could not be reached.");
    this.name = "AuthUnavailableError";
  }
}

/** The credentials were not accepted. Deliberately says no more than that. */
export class CredentialsRejectedError extends Error {
  constructor() {
    super("Those credentials were not accepted.");
    this.name = "CredentialsRejectedError";
  }
}

/** The account could not be created. The API refuses to say why, so nor do we. */
export class RegistrationRefusedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RegistrationRefusedError";
  }
}

export interface Credentials {
  email: string;
  password: string;
}

async function post(path: string, body: Credentials): Promise<Response> {
  try {
    return await fetch(`/api/auth/${path}`, {
      method: "POST",
      credentials: "same-origin",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthUnavailableError();
  }
}

/**
 * Create an account. Does not sign the new account in.
 *
 * Registration and login are separate calls because they are separate endpoints
 * on the API, and collapsing them here would hide which one failed.
 */
export async function register(credentials: Credentials): Promise<void> {
  const response = await post("register", credentials);
  if (response.status === 201) return;
  if (response.status === 409) {
    // The API answers identically however creation failed, so that a stranger
    // cannot learn which addresses have accounts. Repeating its wording keeps
    // that property instead of leaking the distinction in the browser.
    throw new RegistrationRefusedError("That account could not be created.");
  }
  if (response.status === 422) {
    throw new RegistrationRefusedError(
      "Check the address, and use a password of at least 12 characters.",
    );
  }
  throw new AuthUnavailableError();
}

export async function signIn(credentials: Credentials): Promise<void> {
  const response = await post("session", credentials);
  if (response.status === 204) return;
  if (response.status === 401) throw new CredentialsRejectedError();
  if (response.status === 422) throw new CredentialsRejectedError();
  throw new AuthUnavailableError();
}

export async function signOut(): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/auth/session", {
      method: "DELETE",
      credentials: "same-origin",
      headers: { accept: "application/json" },
    });
  } catch {
    throw new AuthUnavailableError();
  }
  if (response.status !== 204) throw new AuthUnavailableError();
}
