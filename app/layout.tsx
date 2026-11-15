import './globals.css';
import type { Metadata } from 'next';

const title = process.env.BOARD_TITLE || 'Jobboard';

export const metadata: Metadata = {
  title,
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
