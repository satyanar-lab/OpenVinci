// Verification identity — what OpenVinci's emitted configs are proven
// to do. These are PLATFORM-level claims, not per-user-project state:
// every level here is exercised by `scripts/verify.sh` and runs on
// every push via GitHub Actions. The UI surfaces them so the user
// understands what "this tool is verified" means without overstating
// what was checked.
//
// Keep this list in lockstep with README.md's verification table. If
// you add a level there, mirror the row here verbatim — the README is
// the source of truth.

export type VerificationCategory = "L1" | "L2" | "L3";

export type VerificationLevel = {
  id: string;
  category: VerificationCategory;
  title: string;
  /** One-line claim, mirroring the README cell. */
  claim: string;
  /** What command exercises it in this repo. */
  target: string;
};

export const VERIFICATION_LEVELS: VerificationLevel[] = [
  {
    id: "l1-validate",
    category: "L1",
    title: "L1 validate",
    claim:
      "Every example loads through the typed model, round-trips serializer ↔ JSON without drift, validates against the Layer-1 JSON Schemas, and passes every engine rule.",
    target: "make test-backend",
  },
  {
    id: "l1-gen-compile",
    category: "L1",
    title: "L1 generate + compile",
    claim:
      "The upstream vendor/as generators emit *_Cfg.{h,c} that parse cleanly with gcc -c -fsyntax-only -Wall against the BSW headers in vendor/as/infras/communication/.",
    target: "pytest backend/tests/test_gen_pipeline.py",
  },
  {
    id: "l2-broker",
    category: "L2",
    title: "L2 broker transport",
    claim:
      "vendor/as's can_simulator broker comes up, accepts clients, transports frames byte-exact between peers, and correctly suppresses sender echoes.",
    target: "TestBrokerLoopback",
  },
  {
    id: "l2-e2e",
    category: "L2",
    title: "L2 end-to-end (generated stack)",
    claim:
      "A real node binary linking our generated *_Cfg.c with Com / CanIf / PduR / Can MCAL + simulator Can driver transmits id 0x100 (Com_SendSignal) and decodes id 0x101 (Com_ReceiveSignal) byte-exact.",
    target: "TestComStackLoopback",
  },
  {
    id: "l2-canfd",
    category: "L2",
    title: "L2 end-to-end CAN FD (generated stack)",
    claim:
      "An FD-marked PDU (fd:true, dlc:16) round-trips a 16-byte UINT8N payload through Com_SendSignal / Com_ReceiveSignal on canfd-minimal; the broker wire dlc is asserted to be 16.",
    target: "TestCanFdLoopback",
  },
  {
    id: "l2-cantp",
    category: "L2",
    title: "L2 end-to-end CanTp segmented (generated stack)",
    claim:
      "ISO-15765 segmented diagnostic transport: a 20-byte SDU sent FF + (FC asserted) + 2× CF reassembles byte-exact through upstream CanTp.c to a Dcm sink; a CF sequence-number gap correctly fails to deliver.",
    target: "TestCanTpLoopback",
  },
  {
    id: "l3-golden",
    category: "L3",
    title: "L3 golden snapshot",
    claim:
      "The exact byte content of every generated file matches a checked-in snapshot for com-minimal, canfd-minimal, and cantp-iso15765 (vendor/as timestamp lines stripped).",
    target: "pytest tests/golden",
  },
];

/** README anchor — kept here so callers don't drift from the docs link. */
export const VERIFICATION_README_URL =
  "https://github.com/satyanar-lab/OpenVinci/blob/main/README.md#how-generated-files-are-verified";

export const VERIFICATION_CI_URL =
  "https://github.com/satyanar-lab/OpenVinci/actions/workflows/verify.yml";
