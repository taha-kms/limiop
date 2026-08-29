import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CredentialsForm } from "./credentials-form";

const register = vi.hoisted(() => vi.fn());
const signIn = vi.hoisted(() => vi.fn());
const replace = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/auth", () => ({ register, signIn }));

async function fillIn(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email address"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button"));
}

describe("CredentialsForm", () => {
  beforeEach(() => {
    register.mockReset().mockResolvedValue(undefined);
    signIn.mockReset().mockResolvedValue(undefined);
    replace.mockReset();
    // Signing in crosses into server-rendered, session-dependent pages, so the
    // form replaces the document rather than navigating within it.
    vi.stubGlobal("location", { replace });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("signs in and returns to where the visitor was going", async () => {
    render(<CredentialsForm mode="sign-in" next="/onboarding" />);

    await fillIn("candidate@example.com", "a-long-enough-password");

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding"));
    expect(signIn).toHaveBeenCalledWith({
      email: "candidate@example.com",
      password: "a-long-enough-password",
    });
    expect(register).not.toHaveBeenCalled();
  });

  it("registering also signs in, because creating an account issues no session", async () => {
    render(<CredentialsForm mode="register" next="/" />);

    await fillIn("new@example.com", "a-long-enough-password");

    await waitFor(() => expect(signIn).toHaveBeenCalled());
    expect(register).toHaveBeenCalledBefore(signIn);
  });

  it("stays put and reports the refusal when signing in fails", async () => {
    signIn.mockRejectedValue(new Error("Those credentials were not accepted."));
    render(<CredentialsForm mode="sign-in" next="/onboarding" />);

    await fillIn("candidate@example.com", "wrong");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Those credentials were not accepted.",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  it("never puts the password anywhere a later render could show it", async () => {
    signIn.mockRejectedValue(new Error("Those credentials were not accepted."));
    render(<CredentialsForm mode="sign-in" next="/" />);

    await fillIn("candidate@example.com", "hunter2-hunter2");

    await screen.findByRole("alert");
    expect(document.body.textContent).not.toContain("hunter2-hunter2");
  });

  it("asks a new account for a password long enough for the API to accept", () => {
    render(<CredentialsForm mode="register" next="/" />);

    expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "12");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
  });

  it("does not put a length floor on signing in, where an old password is still valid", () => {
    render(<CredentialsForm mode="sign-in" next="/" />);

    expect(screen.getByLabelText("Password")).not.toHaveAttribute("minlength");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
  });
});
