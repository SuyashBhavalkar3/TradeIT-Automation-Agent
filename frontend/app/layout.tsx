import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradeIT — Intelligent F&O Trading Engine",
  description: "Automated F&O Algorithmic Trading with Capital Protection, Safe Mode & Anti-Chasing Ceiling",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0b0e14] text-slate-100 antialiased selection:bg-blue-600 selection:text-white">
        {children}
      </body>
    </html>
  );
}

