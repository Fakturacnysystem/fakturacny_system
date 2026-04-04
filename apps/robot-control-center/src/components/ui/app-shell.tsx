"use client";

import React, { type ReactNode } from "react";
import { AnimatePresence, LayoutGroup, MotionConfig, motion } from "motion/react";
import { motionDurations, motionEase, motionSprings, tabTransition } from "@/lib/ui/motion";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export interface AppShellTab {
  id: string;
  label: string;
  detail: string;
  tone: "good" | "warn" | "danger" | "info";
  hotkey: string;
}

interface AppShellProps {
  activeScreen: string;
  screenTabs: AppShellTab[];
  onSelectScreen: (id: AppShellTab["id"]) => void;
  runtimeIdentity: ReactNode;
  actionBar?: ReactNode;
  hero: ReactNode;
  oversight: ReactNode;
  errors?: string[];
  children: ReactNode;
}

export function AppShell({
  activeScreen,
  screenTabs,
  onSelectScreen,
  runtimeIdentity,
  actionBar,
  hero,
  oversight,
  errors = [],
  children,
}: AppShellProps) {
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: motionDurations.standard, ease: motionEase }}>
      <main className="rtc-shell" data-active-screen={activeScreen}>
        <LayoutGroup id="rtc-tabs">
          <section className="rtc-screen-nav-card rtc-card rtc-panel rtc-panel-elevated">
            <div className="rtc-panel-inner rtc-card-inner rtc-screen-nav-inner">
              <div>
                <div className="rtc-section-eyebrow">Operator console</div>
                <h1 className="rtc-screen-nav-title">Robot Control Center</h1>
                <p className="rtc-section-subtitle rtc-screen-nav-subtitle">
                  High-signal operator surface with explicit run truth, safety posture, execution observability, and audit-preserving controls.
                </p>
              </div>
              <div className="rtc-screen-nav-hints">
                <span className="rtc-inline-note">Use keys 1-4 to switch screens</span>
                <span className="rtc-inline-note">Press R to refresh runtime telemetry</span>
              </div>
            </div>
            <div className="rtc-screen-tab-grid">
              {screenTabs.map((tab) => {
                const active = activeScreen === tab.id;
                return (
                  <motion.button
                    key={tab.id}
                    className="rtc-screen-tab"
                    data-active={active}
                    data-tone={tab.tone}
                    type="button"
                    whileHover={active ? undefined : { y: -2 }}
                    whileTap={{ scale: 0.995 }}
                    transition={tabTransition}
                    onClick={() => onSelectScreen(tab.id)}
                  >
                    <span className="rtc-screen-tab-eyebrow">[{tab.hotkey}] screen</span>
                    <span className="rtc-screen-tab-label">{tab.label}</span>
                    <span className="rtc-screen-tab-detail">{tab.detail}</span>
                    {active ? <motion.span className="rtc-screen-tab-indicator" layoutId="rtc-tab-indicator" transition={motionSprings.snappy} /> : null}
                  </motion.button>
                );
              })}
            </div>
          </section>
        </LayoutGroup>

        {actionBar ? <div className="rtc-action-bar-slot">{actionBar}</div> : null}

        {errors.length > 0 ? (
          <section className="rtc-error-strip" aria-live="polite">
            {errors.slice(0, 3).map((error) => (
              <div className="rtc-banner rtc-banner-compact" data-tone="danger" key={error}>{error}</div>
            ))}
          </section>
        ) : null}

        {runtimeIdentity}
        {hero}
        {oversight}

        <AnimatePresence mode="wait">
          <motion.div
            key={activeScreen}
            className="rtc-screen-slot"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={motionSprings.smooth}
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>
    </MotionConfig>
  );
}
