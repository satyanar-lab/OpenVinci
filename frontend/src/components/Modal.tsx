import type { ReactNode } from "react";
import { X } from "lucide-react";

/**
 * Generic dialog shell. Title-and-icon header, body, and a footer
 * area the callers fill in. Click on the backdrop closes; click on
 * the modal surface does not, so a slightly-off click doesn't lose
 * the user's work.
 */
export function Modal({
  title,
  icon,
  onClose,
  children,
}: {
  title: string;
  icon?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h3 className="modal-title">
            {icon && <span className="modal-icon">{icon}</span>}
            <span>{title}</span>
          </h3>
          <button
            onClick={onClose}
            className="modal-close icon-only"
            aria-label="close"
            title="close"
          >
            <X size={14} aria-hidden />
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
