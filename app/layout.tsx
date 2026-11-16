import './globals.css';
import type { Metadata, Viewport } from 'next';
import Nav from './Nav';

const title = process.env.BOARD_TITLE || 'Jobboard';

export const metadata: Metadata = {
  title,
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f5f5f7' },
    { media: '(prefers-color-scheme: dark)', color: '#000000' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>
        <Nav title={title} />
        {children}
      </body>
    </html>
  );
}
