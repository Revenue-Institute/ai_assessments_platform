import { brandFontShell } from "@repo/design-system/lib/fonts";
import { ThemeProvider } from "@repo/design-system/providers/theme";
import { Toaster } from "@repo/design-system/components/ui/sonner";
import { TooltipProvider } from "@repo/design-system/components/ui/tooltip";
import type { Metadata } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import "./styles.css";

const headingFont = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-heading",
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
});

// Satoshi (variable) — licensed self-hosted woff2 at
// app/fonts/Satoshi-Variable.woff2 (compressed from the source ttf
// via `woff2_compress`).
const bodyFont = localFont({
  src: "./fonts/Satoshi-Variable.woff2",
  variable: "--font-sans",
  display: "swap",
  weight: "300 900",
});

export const metadata: Metadata = {
  title: "Revenue Institute Assessments",
  description: "Internal assessments platform.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      className={brandFontShell(headingFont.variable, bodyFont.variable)}
      lang="en"
      suppressHydrationWarning
    >
      <body>
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem>
          <TooltipProvider>{children}</TooltipProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
