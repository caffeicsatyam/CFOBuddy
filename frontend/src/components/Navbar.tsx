'use client';

import Link from 'next/link';
import { useState } from 'react';
import styles from './Navbar.module.css';

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <nav className={styles.nav}>
      <div className={styles.inner}>
        {/* Logo */}
        <Link href="/" className={styles.logo}>
          <span className={styles.logoIcon}>✦</span>
          <span>CFOBuddy</span>
        </Link>

        {/* Desktop links */}
        <ul className={styles.links}>
          {['Features'].map((item) => (
            <li key={item}>
              <Link
                href={`#${item.toLowerCase()}`}
                className={styles.link}
              >
                {item}
              </Link>
            </li>
          ))}
        </ul>

        {/* CTA */}
        <div className={styles.actions}>
          <Link href="/login" className={styles.link} style={{ marginRight: '0.5rem' }}>
            Sign in
          </Link>
          <Link href="/signup" className="btn btn-accent btn-sm">
            Get started →
          </Link>
          <button
            className={styles.burger}
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Toggle menu"
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {menuOpen && (
        <div className={styles.mobile}>
          {['Features'].map((item) => (
            <Link
              key={item}
              href={`#${item.toLowerCase()}`}
              className={styles.mobileLink}
              onClick={() => setMenuOpen(false)}
            >
              {item}
            </Link>
          ))}
          <Link href="/login" className={styles.mobileLink} onClick={() => setMenuOpen(false)}>
            Sign in
          </Link>
          <Link href="/signup" className="btn btn-accent btn-sm" onClick={() => setMenuOpen(false)}>
            Get started →
          </Link>
        </div>
      )}
    </nav>
  );
}
