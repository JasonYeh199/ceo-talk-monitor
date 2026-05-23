import "./globals.css";

export const metadata = {
  title: "CEO Talk Monitor",
  description: "Investment research monitor for executive interviews.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

