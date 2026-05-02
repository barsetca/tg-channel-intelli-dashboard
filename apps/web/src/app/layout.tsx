import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Channel Intelligence",
  description: "Telegram channel analytics and AI search",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
