"use client";

import React, { type ReactNode } from "react";
import { motion } from "motion/react";
import { motionSprings } from "@/lib/ui/motion";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

interface FloatingActionBarProps {
  title: string;
  subtitle: string;
  status?: ReactNode;
  primary: ReactNode;
  danger?: ReactNode;
  aside?: ReactNode;
  className?: string;
}

export function FloatingActionBar({ title, subtitle, status, primary, danger, aside, className }: FloatingActionBarProps) {
  return (
    <motion.aside
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={motionSprings.smooth}
      className={cx("rtc-floating-bar", className)}
    >
      <div className="rtc-floating-bar-copy">
        <div className="rtc-floating-bar-title-row">
          <h2 className="rtc-floating-bar-title">{title}</h2>
          {status ? <div className="rtc-floating-bar-status">{status}</div> : null}
        </div>
        <p className="rtc-floating-bar-subtitle">{subtitle}</p>
      </div>
      <div className="rtc-floating-bar-actions">
        <div className="rtc-floating-bar-cluster">{primary}</div>
        {danger ? <div className="rtc-floating-bar-cluster rtc-floating-bar-cluster-danger">{danger}</div> : null}
        {aside ? <div className="rtc-floating-bar-aside">{aside}</div> : null}
      </div>
    </motion.aside>
  );
}
