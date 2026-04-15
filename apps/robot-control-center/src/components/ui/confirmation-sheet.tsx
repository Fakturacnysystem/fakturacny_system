"use client";

import React, { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { motionSprings, overlayTransition } from "@/lib/ui/motion";

type Tone = "good" | "warn" | "danger" | "info";

interface ConfirmationSheetProps {
  open: boolean;
  title: string;
  subtitle: string;
  tone?: Tone;
  reason?: string;
  detail?: string;
  auditNote?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmationSheet({
  open,
  title,
  subtitle,
  tone = "warn",
  reason,
  detail,
  auditNote,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
}: ConfirmationSheetProps) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.setTimeout(() => confirmRef.current?.focus(), 10);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="rtc-confirm-sheet-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={overlayTransition}
        >
          <motion.div
            aria-labelledby="rtc-confirm-title"
            aria-modal="true"
            className="rtc-confirm-sheet"
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            role="dialog"
            transition={motionSprings.smooth}
          >
            <div className="rtc-confirm-sheet-header">
              <span className="rtc-pill" data-tone={tone}>confirmation required</span>
              <h2 className="rtc-screen-title rtc-confirm-sheet-title" id="rtc-confirm-title">{title}</h2>
              <p className="rtc-section-subtitle rtc-confirm-sheet-subtitle">{subtitle}</p>
            </div>
            <div className="rtc-confirm-sheet-body">
              {detail ? <div className="rtc-banner" data-tone={tone === "danger" ? "danger" : "warn"}>{detail}</div> : null}
              <div className="rtc-kv rtc-confirm-sheet-kv">
                <div className="rtc-kv-row">
                  <span>Reason text</span>
                  <strong>{reason || "unavailable"}</strong>
                </div>
                <div className="rtc-kv-row">
                  <span>Audit posture</span>
                  <strong>{auditNote || "This action will be written through the runtime control endpoint."}</strong>
                </div>
              </div>
            </div>
            <div className="rtc-confirm-sheet-actions">
              <button className="rtc-button rtc-button-quiet" type="button" onClick={onCancel}>
                {cancelLabel}
              </button>
              <button ref={confirmRef} className="rtc-button" data-variant={tone === "danger" ? "danger" : undefined} type="button" onClick={onConfirm}>
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
