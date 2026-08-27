import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SALVAGE — Recovery Decision Agent",
  description: "AI Revenue Recovery for Razorpay merchants (Track 03).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
