import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MarkFlow Web",
  description: "Step-based document extraction dashboard for MarkFlow.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
