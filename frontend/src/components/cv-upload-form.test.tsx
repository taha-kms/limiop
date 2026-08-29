import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CVUploadForm } from "./cv-upload-form";

const fetchMock = vi.fn();
const reload = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  reload.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("location", { reload });
});
afterEach(() => vi.unstubAllGlobals());

async function upload() {
  const file = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText(/Your CV|Replace your CV/), file);
  await userEvent.click(screen.getByRole("button"));
}

describe("CVUploadForm", () => {
  it("posts the file same-origin and reloads so the new state renders", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 201 }));
    render(<CVUploadForm current={null} />);

    await upload();

    await waitFor(() => expect(reload).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/cv");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it.each([
    ["file_too_large", /over 5 MB/],
    ["unsupported_media_type", /Only PDFs are accepted/],
    ["unsupported_content", /not a PDF, whatever its name says/],
    ["empty_file", /file is empty/],
  ])("renders %s as something to act on", async (code, expected) => {
    fetchMock.mockResolvedValue(Response.json({ detail: { code, message: "x" } }, { status: 415 }));
    render(<CVUploadForm current={null} />);

    await upload();

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(reload).not.toHaveBeenCalled();
  });

  it("shows an unrecognised refusal rather than inventing a reassuring one", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ detail: { code: "something_new" } }, { status: 400 }),
    );
    render(<CVUploadForm current={null} />);

    await upload();

    expect(await screen.findByRole("alert")).toHaveTextContent("something_new");
  });

  it("says the upload could not be sent when the request fails outright", async () => {
    fetchMock.mockRejectedValue(new TypeError("network"));
    render(<CVUploadForm current={null} />);

    await upload();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be sent/);
  });

  it("calls a second upload a replacement", () => {
    render(
      <CVUploadForm
        current={{
          id: "cv-1",
          media_type: "application/pdf",
          size_bytes: 1,
          processing_state: "processed",
          created_at: "2026-08-29T10:00:00Z",
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Replace CV" })).toBeVisible();
    expect(screen.getByLabelText("Replace your CV")).toBeVisible();
  });

  it("refuses to send nothing", async () => {
    render(<CVUploadForm current={null} />);

    await userEvent.click(screen.getByRole("button"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a PDF to upload.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
