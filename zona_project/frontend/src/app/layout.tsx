import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "cyrillic"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Foydali", template: "%s · Foydali" },
  description: "Foydali — StarGroup IT platformasi: support bot, PRBC vazifalari, IT inventarizatsiya, mas'uliyat xaritasi.",
  applicationName: "Foydali",
};

/** Ildiz layout (Server Component): statik qobiq. Brauzerga bog'liq hamma narsa provayderlar ichida. */
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="uz" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="h-full overflow-hidden">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
