import type { Metadata } from 'next';
import { Manrope, Inter } from 'next/font/google';
import './globals.css';

const manrope = Manrope({
  subsets: ['latin'],
  variable: '--font-headline-loaded',
  display: 'swap',
  weight: ['400', '500', '600', '700', '800'],
});

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-body-loaded',
  display: 'swap',
  weight: ['300', '400', '500', '600'],
});

export const metadata: Metadata = {
  title: 'CFOBuddy | Precision AI Financial Analyst',
  description:
    'CFOBuddy is an AI-powered financial assistant. Ask questions about financial statements, customer accounts, stocks, and more.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${manrope.variable} ${inter.variable}`} data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
