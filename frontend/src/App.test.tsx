import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { buildTree, findNodeById } from "./treeModel";
import { schemaAt } from "./schemaWalk";

// Minimal schemas (subset) — exercise resolve + walk without dragging
// the full Layer-1 schemas into the test bundle.
const schemas = {
  Can: {
    type: "object",
    properties: {
      class: { const: "Can" },
      controllers: {
        type: "array",
        items: { type: "object", properties: { name: { type: "string" } } },
      },
    },
  },
  CanIf: {
    type: "object",
    properties: {
      class: { const: "CanIf" },
      networks: { type: "array", items: { type: "object" } },
    },
  },
  CanTp: {
    type: "object",
    properties: {
      class: { const: "CanTp" },
      channels: { type: "array", items: { type: "object" } },
    },
  },
  PduR: {
    type: "object",
    properties: {
      class: { const: "PduR" },
      routines: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name: { type: "string" },
            from: { type: "string" },
            to: { type: "string" },
          },
        },
      },
    },
  },
  Com: {
    type: "object",
    properties: {
      class: { const: "Com" },
      networks: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name: { type: "string" },
            me: { type: "string" },
            baudrate: { type: "integer", minimum: 1 },
            messages: { type: "array", items: { type: "object" } },
          },
        },
      },
    },
  },
};

const sampleProject = {
  Com: {
    class: "Com",
    networks: [
      {
        name: "CAN0",
        network: "CAN",
        me: "AS",
        baudrate: 500000,
        messages: [
          {
            name: "STATUS",
            id: "0x100",
            dlc: 8,
            node: "AS",
            signals: [
              { name: "Counter", start: 0, size: 8, endian: "little" },
            ],
          },
        ],
      },
    ],
  },
  CanIf: {
    class: "CanIf",
    networks: [
      {
        name: "CAN0",
        RxPdus: [],
        TxPdus: [{ name: "CAN0_STATUS_TX", id: "0x100", hoh: 0, up: "PduR" }],
      },
    ],
  },
  PduR: {
    class: "PduR",
    routines: [{ name: "CAN0_STATUS_TX", from: "Com", to: "CanIf" }],
  },
  Can: {
    class: "Can",
    controllers: [
      { name: "CAN0", hwInstanceId: 0, baudrate: 500000, device: "simulator_v2" },
    ],
  },
};

const validationOk = {
  ok: true,
  errorCount: 0,
  warningCount: 0,
  issues: [],
};

const validationWithFix = {
  ok: false,
  errorCount: 1,
  warningCount: 0,
  issues: [
    {
      rule: "demo.example",
      severity: "error",
      message: "Demo issue with auto-fix",
      module: "Can",
      path: [],
      fix: {
        description: "Add a thing",
        patches: { Can: [{ op: "add", path: "/controllers/-", value: {} }] },
      },
    },
  ],
};

function mockFetch(byPath: Record<string, () => Response>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
    const handler = byPath[path] ?? byPath["*"];
    if (!handler) throw new Error(`unexpected fetch: ${url}`);
    return handler();
  });
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("schemaWalk", () => {
  it("descends through properties and items", () => {
    const at = schemaAt(schemas.Com, ["networks", 0, "name"]);
    expect(at.type).toBe("string");
    const integerSchema = schemaAt(schemas.Com, ["networks", 0, "baudrate"]);
    expect(integerSchema.type).toBe("integer");
  });

  it("returns empty schema for unknown segment", () => {
    const at = schemaAt(schemas.Com, ["nope"]);
    expect(at).toEqual({});
  });
});

describe("treeModel", () => {
  it("builds a hierarchical tree from real project shape", () => {
    const tree = buildTree(sampleProject);
    const labels = tree.map((n) => n.label);
    expect(labels).toEqual(["Can", "CanIf", "PduR", "Com"]);

    const com = tree.find((n) => n.label === "Com")!;
    const network = com.children!.find((n) => n.label === "CAN0")!;
    expect(network.kind).toBe("item");
    const status = network.children!.find((n) => n.label === "STATUS")!;
    expect(status.children![0].label).toBe("Counter");
  });

  it("findNodeById walks deep paths", () => {
    const tree = buildTree(sampleProject);
    expect(findNodeById(tree, "Com/networks/0/messages/0")?.label).toBe(
      "STATUS",
    );
  });
});

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/schemas": () => jsonResponse(schemas),
        "/api/projects": () =>
          jsonResponse({ projects: ["com-minimal", "canapp-min"] }),
        "/api/projects/com-minimal": () =>
          jsonResponse({ name: "com-minimal", project: sampleProject }),
        "/api/validate": () => jsonResponse(validationWithFix),
        "/api/apply-fix": () =>
          jsonResponse({
            project: sampleProject,
            validation: validationOk,
          }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("boots, loads project, builds tree", async () => {
    render(<App />);
    expect(screen.getByText("OpenVinci")).toBeInTheDocument();
    // Tree shows module headings
    await waitFor(() =>
      expect(screen.getByText("Com")).toBeInTheDocument(),
    );
    expect(screen.getByText("Can")).toBeInTheDocument();
    expect(screen.getByText("PduR")).toBeInTheDocument();
  });

  it("shows validation issues after load and offers Fix button", async () => {
    render(<App />);
    await waitFor(() =>
      expect(
        screen.getByText("Demo issue with auto-fix"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Fix" })).toBeInTheDocument();
  });

  it("applies a fix when Fix is clicked", async () => {
    render(<App />);
    const fixBtn = await screen.findByRole("button", { name: "Fix" });
    await act(async () => {
      fireEvent.click(fixBtn);
    });
    // After fix the validation reports ok; counts badge should show
    await waitFor(() =>
      expect(screen.getByText(/no issues/i)).toBeInTheDocument(),
    );
  });

  it("Import DBC opens a modal", async () => {
    render(<App />);
    await waitFor(() =>
      expect(screen.getByText("Com")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Import DBC/i }));
    expect(screen.getByRole("dialog", { name: /Import DBC/i })).toBeInTheDocument();
  });
});
