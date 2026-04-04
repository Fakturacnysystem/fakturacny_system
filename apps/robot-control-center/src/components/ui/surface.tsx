"use client";

import React, { type PropsWithChildren, type ReactNode } from "react";
import { motion } from "motion/react";
import { fadeUp, panelTransition, staggerItem } from "@/lib/ui/motion";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type Tone = "good" | "warn" | "danger" | "info" | "neutral";

interface GlassPanelProps extends PropsWithChildren {
  className?: string;
  tone?: Tone;
  elevated?: boolean;
  interactive?: boolean;
  compact?: boolean;
  role?: string;
}

export function GlassPanel({
  children,
  className,
  tone = "neutral",
  elevated = false,
  interactive = false,
  compact = false,
  role,
}: GlassPanelProps) {
  return (
    <motion.section
      {...fadeUp}
      transition={panelTransition}
      className={cx(
        "rtc-panel",
        "rtc-card",
        elevated && "rtc-panel-elevated",
        interactive && "rtc-panel-interactive",
        compact && "rtc-panel-compact",
        tone !== "neutral" && `rtc-panel-tone-${tone}`,
        className,
      )}
      role={role}
    >
      <div className="rtc-panel-inner rtc-card-inner">{children}</div>
    </motion.section>
  );
}

interface SectionHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
}

export function SectionHeader({ eyebrow, title, subtitle, meta, actions, compact = false }: SectionHeaderProps) {
  return (
    <div className={cx("rtc-section-header", compact && "rtc-section-header-compact")}>
      <div className="rtc-section-heading-block">
        {eyebrow ? <div className="rtc-section-eyebrow">{eyebrow}</div> : null}
        <h2 className="rtc-section-title">{title}</h2>
        {subtitle ? <p className="rtc-section-subtitle">{subtitle}</p> : null}
      </div>
      {meta || actions ? (
        <div className="rtc-section-header-side">
          {meta ? <div className="rtc-section-meta">{meta}</div> : null}
          {actions ? <div className="rtc-section-actions">{actions}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

interface StatusBadgeProps {
  tone?: Exclude<Tone, "neutral">;
  label?: string;
  value: ReactNode;
  subtle?: boolean;
}

export function StatusBadge({ tone = "info", label, value, subtle = false }: StatusBadgeProps) {
  return (
    <span className={cx("rtc-pill", "rtc-badge", subtle && "rtc-pill-subtle")} data-tone={tone}>
      {label ? <strong>{label}</strong> : null}
      <span>{value}</span>
    </span>
  );
}

interface MetricCardProps {
  label: string;
  value: ReactNode;
  hint: string;
  tone?: Exclude<Tone, "neutral">;
  emphasis?: boolean;
}

export function MetricCard({ label, value, hint, tone = "info", emphasis = false }: MetricCardProps) {
  return (
    <motion.article
      variants={staggerItem}
      className={cx("rtc-metric", emphasis && "rtc-metric-emphasis")}
      data-tone={tone}
    >
      <div className="rtc-metric-label">{label}</div>
      <div className="rtc-metric-value">{value}</div>
      <div className="rtc-metric-hint">{hint}</div>
    </motion.article>
  );
}

interface DetailListItem {
  label: string;
  value: ReactNode;
}

export function DetailList({ items, className }: { items: DetailListItem[]; className?: string }) {
  return (
    <div className={cx("rtc-kv", className)}>
      {items.map((item) => (
        <div className="rtc-kv-row" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

interface LiveFeedListProps<T> {
  title: string;
  subtitle: string;
  items: T[];
  empty: ReactNode;
  className?: string;
  layout?: "two" | "three";
  renderItem: (item: T) => ReactNode;
}

export function LiveFeedList<T>({
  title,
  subtitle,
  items,
  empty,
  className,
  layout = "three",
  renderItem,
}: LiveFeedListProps<T>) {
  return (
    <div className={cx("rtc-subpanel", className)}>
      <SectionHeader title={title} subtitle={subtitle} compact />
      <div className={cx("rtc-feed-grid", layout === "two" ? "rtc-feed-grid-two" : "rtc-feed-grid-three")}>
        {items.length > 0 ? items.map(renderItem) : <div className="rtc-feed-empty">{empty}</div>}
      </div>
    </div>
  );
}
