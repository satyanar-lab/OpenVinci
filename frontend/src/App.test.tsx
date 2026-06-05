import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            project: "canapp-min",
            module: "Com",
            source: "examples/canapp-min/config/Com/Com.json",
            data: { class: "Com", networks: [{ name: "CAN0" }] },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the title", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /OpenVinci/i })).toBeInTheDocument();
  });

  it("fetches and displays the Com config", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText(/examples\/canapp-min\/config\/Com\/Com\.json/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/"class": "Com"/)).toBeInTheDocument();
  });
});
