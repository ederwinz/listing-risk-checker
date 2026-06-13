import type { Metadata } from "next";
import { Hanken_Grotesk, Source_Serif_4, Geist_Mono } from "next/font/google";
import "./globals.css";

const bodyFont = Hanken_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-body",
  display: "swap",
});
const headFont = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-head",
  display: "swap",
});
const monoFont = Geist_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Counterpart — Listing Checker",
  description:
    "Check overseas listings against official brand records. Reports mismatch risk only.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${bodyFont.variable} ${headFont.variable} ${monoFont.variable} h-full`}
    >
      <head>
        <meta name="color-scheme" content="light" />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
