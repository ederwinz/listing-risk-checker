import type { Metadata } from "next";
import { Hanken_Grotesk, Source_Serif_4, Geist_Mono, Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";
import "../globals.css";
import { getDict, LANGS } from "@/app/dictionaries";

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
const cjkBody = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body-cjk",
  display: "swap",
});
const cjkHead = Noto_Serif_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-head-cjk",
  display: "swap",
});

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: string }>;
}): Promise<Metadata> {
  const { lang } = await params;
  const t = getDict(lang);
  return { title: t.metaTitle, description: t.metaDescription };
}

export default async function RootLayout({
  children,
  params,
}: Readonly<{ children: React.ReactNode; params: Promise<{ lang: string }> }>) {
  const { lang } = await params;
  const cjk = lang === "zh" ? `${cjkBody.variable} ${cjkHead.variable}` : "";

  return (
    <html
      lang={lang}
      className={`${bodyFont.variable} ${headFont.variable} ${monoFont.variable} ${cjk} h-full`}
    >
      <head>
        <meta name="color-scheme" content="light" />
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
