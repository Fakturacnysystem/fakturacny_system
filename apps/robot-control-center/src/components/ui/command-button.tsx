"use client";

import React, { type ReactNode } from "react";
import { motion, type HTMLMotionProps } from "motion/react";
import { motionSprings } from "@/lib/ui/motion";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type Tone = "good" | "warn" | "danger" | "info";

interface CommandButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  label: string;
  detail?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  pending?: boolean;
  active?: boolean;
}

export function CommandButton({
  label,
  detail,
  tone = "info",
  icon,
  pending = false,
  active = false,
  className,
  disabled,
  ...props
}: CommandButtonProps) {
  return (
    <motion.button
      whileHover={disabled ? undefined : { y: -2, scale: 1.01 }}
      whileTap={disabled ? undefined : { scale: 0.99 }}
      transition={motionSprings.snappy}
      className={cx("rtc-command-button", active && "rtc-command-button-active", className)}
      data-tone={tone}
      disabled={disabled || pending}
      type="button"
      {...props}
    >
      <span className="rtc-command-button-topline">
        <span className="rtc-command-button-icon" aria-hidden="true">{icon ?? "•"}</span>
        <span className="rtc-command-button-label">{pending ? "Applying…" : label}</span>
      </span>
      {detail ? <span className="rtc-command-button-detail">{detail}</span> : null}
    </motion.button>
  );
}
