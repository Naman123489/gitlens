import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AuthProvider } from "@/lib/auth-context";

import "./globals.css";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "RepoLens — Know What a GitHub Profile Really Proves",
    template: "%s · RepoLens",
  },
  description:
    "Evaluate engineering ability, project relevance, code quality and AI-assisted development " +
    "using evidence from real repositories.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className={`${sans.variable} ${mono.variable} font-sans`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
