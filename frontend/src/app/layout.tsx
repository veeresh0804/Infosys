import "./globals.css";
import React from "react";

export const metadata = {
  title: "AI-Driven Smart Farming Assistant | Milestones 1 & 2 Test Interface",
  description: "Multilingual AI Agricultural Guidance and Farmer Support with Indic Speech, RAG Knowledge Base, and Live Agronomic Data."
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
