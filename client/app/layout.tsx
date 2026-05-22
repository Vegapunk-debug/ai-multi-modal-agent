import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Lingua — Voice Tutor",
  description: "Voice-first multilingual language tutor",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="ambient">{children}</body>
    </html>
  );
}
