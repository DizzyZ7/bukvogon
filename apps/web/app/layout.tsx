import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import './globals.css';
import './race-visuals.css';

export const metadata: Metadata = {
  title: 'БуквоГон — печатай быстрее, приходи первым',
  description: 'Русскоязычные гонки на скорость и точность печати.',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
