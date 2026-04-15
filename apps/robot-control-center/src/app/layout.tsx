import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { IBM_Plex_Mono, Sora, Space_Grotesk } from "next/font/google";

const displayFont = Sora({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "600", "700"],
});

const bodyFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "700"],
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Riadiaci panel robota",
  description: "Zrozumiteľný riadiaci panel pre sledovanie a bezpečné ovládanie obchodného robota.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="sk" data-theme="dark">
      <body className={`${displayFont.variable} ${bodyFont.variable} ${monoFont.variable}`}>{children}</body>
    </html>
  );
}
