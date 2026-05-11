import type { Metadata, Viewport } from 'next';
import './globals.css';
import GlobalProgressBar from '@/components/GlobalProgressBar';

export const metadata: Metadata = {
  title: 'YouTube Factory',
  description: '動画生成管理パネル',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  themeColor: '#0f172a',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body className="min-h-screen">
        <GlobalProgressBar />
        {children}
      </body>
    </html>
  );
}
