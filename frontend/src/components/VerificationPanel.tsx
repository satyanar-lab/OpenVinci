import {
  Activity,
  Check,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { Modal } from "./Modal";
import {
  VERIFICATION_CI_URL,
  VERIFICATION_LEVELS,
  VERIFICATION_README_URL,
  type VerificationCategory,
} from "../verification";

/**
 * Verification panel. Reflects the 7 levels OpenVinci's CI runs on
 * every push. Honest framing: these are PLATFORM-level claims about
 * what the tool's emitted configs do on the host simulator — not a
 * statement about the user's current edits.
 */
export function VerificationPanel({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      title="Verification"
      icon={<ShieldCheck size={14} aria-hidden />}
      onClose={onClose}
    >
      <p className="hint">
        OpenVinci ships {VERIFICATION_LEVELS.length} verification levels.
        Each makes one <em>specific</em> claim about what the tool's
        emitted configs do on the host simulator — together they cover
        validation, generate+compile, runtime loopback (classic / FD /
        CanTp), and byte-stable golden snapshots. They run on every
        push via GitHub Actions; the README is the source of truth.
      </p>

      <div className="verify-list">
        {VERIFICATION_LEVELS.map((lvl) => (
          <article
            key={lvl.id}
            className={`verify-row cat-${lvl.category.toLowerCase()}`}
            aria-label={lvl.title}
          >
            <span className="verify-mark" aria-hidden>
              <Check size={14} />
            </span>
            <span className={`verify-cat cat-${lvl.category.toLowerCase()}`}>
              {lvl.category}
            </span>
            <div className="verify-body">
              <h4 className="verify-title">{lvl.title}</h4>
              <p className="verify-claim">{lvl.claim}</p>
              <code className="verify-target">{lvl.target}</code>
            </div>
          </article>
        ))}
      </div>

      <p className="hint verify-disclaimer">
        These prove what's claimed and nothing more. No BRS / data-phase
        timing / MCAL hardware (host-sim only); CanTp covers segmented
        Rx of a single FF+FC+CFs cycle, not multi-block STmin pacing or
        Tx initiation. See the "What these levels do NOT claim" section
        of the README.
      </p>

      <div className="modal-footer">
        <a
          className="link verify-link"
          href={VERIFICATION_README_URL}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink size={12} aria-hidden /> README
        </a>
        <a
          className="link verify-link"
          href={VERIFICATION_CI_URL}
          target="_blank"
          rel="noreferrer"
        >
          <Activity size={12} aria-hidden /> CI runs
        </a>
        <span style={{ flex: 1 }} />
        <button onClick={onClose} className="primary">
          Close
        </button>
      </div>
    </Modal>
  );
}

/** Tiny helper exported in case callers want to colour-code by tier. */
export function categoryColor(cat: VerificationCategory): string {
  switch (cat) {
    case "L1":
      return "var(--sev-info)";
    case "L2":
      return "var(--accent)";
    case "L3":
      return "var(--sev-ok)";
  }
}
