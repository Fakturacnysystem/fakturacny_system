"use client";

import React from "react";
import { motion } from "motion/react";
import { fadeUp, motionDurations, motionEase } from "@/lib/ui/motion";
import { SectionHeader } from "@/components/ui/surface";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

interface StateProps {
  title: string;
  description: string;
  detail?: string;
  className?: string;
}

export function EmptyState({ title, description, detail, className }: StateProps) {
  return (
    <motion.div {...fadeUp} transition={{ duration: motionDurations.fast, ease: motionEase }} className={cx("rtc-state-empty", className)}>
      <SectionHeader eyebrow="Prázdny stav" title={title} subtitle={description} compact />
      {detail ? <p className="rtc-inline-note">{detail}</p> : null}
    </motion.div>
  );
}

export function ErrorState({ title, description, detail, className }: StateProps) {
  return (
    <motion.div {...fadeUp} transition={{ duration: motionDurations.fast, ease: motionEase }} className={cx("rtc-state-error", className)}>
      <SectionHeader eyebrow="Chyba" title={title} subtitle={description} compact />
      {detail ? <div className="rtc-banner rtc-banner-compact" data-tone="danger">{detail}</div> : null}
    </motion.div>
  );
}

export function SkeletonState({
  blocks = 3,
  className,
  compact = false,
}: {
  blocks?: number;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cx("rtc-skeleton", compact && "rtc-skeleton-compact", className)} aria-hidden="true">
      {Array.from({ length: blocks }).map((_, index) => (
        <div className="rtc-skeleton-block" key={`skeleton-${index}`}>
          <div className="rtc-skeleton-line rtc-skeleton-line-short" />
          <div className="rtc-skeleton-line rtc-skeleton-line-long" />
          <div className="rtc-skeleton-line rtc-skeleton-line-medium" />
        </div>
      ))}
    </div>
  );
}
