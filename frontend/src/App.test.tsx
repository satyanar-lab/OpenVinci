import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { buildTree, findNodeById } from "./treeModel";
import { schemaAt } from "./schemaWalk";
import { unzipStored } from "./unzipStored";

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

// jsdom's Blob lacks both arrayBuffer() and stream() in older
// releases, which breaks the Response() polyfill we'd otherwise use.
// Roll our own via FileReader. Real browsers ship arrayBuffer
// natively; this only affects unit-test scaffolding.
if (typeof Blob.prototype.arrayBuffer !== "function") {
  (Blob.prototype as unknown as { arrayBuffer: () => Promise<ArrayBuffer> }).arrayBuffer =
    function () {
      const blob = this as Blob;
      return new Promise<ArrayBuffer>((resolve, reject) => {
        const r = new FileReader();
        r.onerror = () => reject(r.error);
        r.onload = () => resolve(r.result as ArrayBuffer);
        r.readAsArrayBuffer(blob);
      });
    };
}

describe("unzipStored", () => {
  // Hand-built two-entry STORED zip — same encoding as Python's
  // zipfile.ZIP_STORED that the backend emits. Validates the inline
  // parser's local-file-header walk + name/data extraction.
  function makeStoredZip(): Blob {
    const enc = new TextEncoder();
    const entries = [
      { name: "GEN/a.txt", data: enc.encode("hello\n") },
      { name: "GEN/sub/b.txt", data: enc.encode("world") },
    ];

    const chunks: Uint8Array[] = [];
    for (const e of entries) {
      const nameBytes = enc.encode(e.name);
      const lfh = new Uint8Array(30);
      const dv = new DataView(lfh.buffer);
      dv.setUint32(0, 0x04034b50, true);  // signature
      dv.setUint16(4, 20, true);            // version needed
      dv.setUint16(6, 0, true);             // gp flag
      dv.setUint16(8, 0, true);             // method = STORED
      dv.setUint32(14, 0, true);            // crc (test doesn't check)
      dv.setUint32(18, e.data.length, true);// compressed size
      dv.setUint32(22, e.data.length, true);// uncompressed size
      dv.setUint16(26, nameBytes.length, true);
      dv.setUint16(28, 0, true);            // extra len
      chunks.push(lfh, nameBytes, e.data);
    }
    // Trailing bytes (a stray Central Directory signature) — the
    // parser should stop cleanly at the first non-LFH signature.
    const cd = new Uint8Array(4);
    new DataView(cd.buffer).setUint32(0, 0x02014b50, true);
    chunks.push(cd);

    const total = chunks.reduce((acc, c) => acc + c.length, 0);
    const out = new Uint8Array(total);
    let off = 0;
    for (const c of chunks) {
      out.set(c, off);
      off += c.length;
    }
    return new Blob([out], { type: "application/zip" });
  }

  it("parses STORED entries and preserves their paths", async () => {
    const entries = await unzipStored(makeStoredZip());
    expect(entries.map((e) => e.path)).toEqual(["GEN/a.txt", "GEN/sub/b.txt"]);
    const dec = new TextDecoder();
    expect(dec.decode(entries[0].content)).toBe("hello\n");
    expect(dec.decode(entries[1].content)).toBe("world");
  });
});

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
        "/api/dbcs": () =>
          jsonResponse({ dbcs: ["examples/dbc/sample.dbc"] }),
        "/api/import/dbc/upload": () =>
          jsonResponse({
            source: "uploaded.dbc",
            network: "CAN0",
            me: "AS",
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
    // After fix the validation reports ok; the panel should switch
    // to the success state (the literal "no issues" badge was renamed
    // to "No problems — configuration valid" when the panel got the
    // IDE pass; this is a deliberate selector update).
    await waitFor(() =>
      expect(
        screen.getByText(/No problems — configuration valid/i),
      ).toBeInTheDocument(),
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

  it("Import DBC modal renders a drop zone", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Com")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Import DBC/i }));
    await waitFor(() =>
      expect(screen.getByTestId("dbc-dropzone")).toBeInTheDocument(),
    );
    expect(screen.getByText(/drop a \.dbc here/i)).toBeInTheDocument();
  });

  it("accepting a dropped .dbc file enables the Import button", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Com")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Import DBC/i }));
    const dropzone = await screen.findByTestId("dbc-dropzone");
    const file = new File(["VERSION \"\""], "test.dbc", {
      type: "application/octet-stream",
    });
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [file] },
    });
    await waitFor(() =>
      expect(screen.getByText(/test\.dbc/)).toBeInTheDocument(),
    );
    const importBtn = screen.getByRole("button", { name: /^Import$/ });
    expect(importBtn).not.toBeDisabled();
  });

  it("rejects non-.dbc drops with an error message", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Com")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Import DBC/i }));
    const dropzone = await screen.findByTestId("dbc-dropzone");
    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [new File(["{}"], "schema.json", { type: "application/json" })],
      },
    });
    await waitFor(() =>
      expect(screen.getByText(/not a \.dbc file/i)).toBeInTheDocument(),
    );
  });
});
