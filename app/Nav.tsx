'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/', label: 'Stellen' },
  { href: '/laeufe', label: 'Läufe' },
  { href: '/suchprofil', label: 'Suchprofil' },
];

export default function Nav({ title }: { title: string }) {
  const path = usePathname();
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link href="/" className="brand">{title}</Link>
        <nav aria-label="Hauptnavigation">
          {LINKS.map((l) => {
            const active = l.href === '/' ? path === '/' : path.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
