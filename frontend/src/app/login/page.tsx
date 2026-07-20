'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, useCallback } from 'react';
import { login, getCurrentUser } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please enter your username and password.');
      return;
    }
    setIsLoading(true);
    setError('');
    try {
      await login(username.trim(), password);
      await getCurrentUser();
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed. Check your credentials.');
    } finally {
      setIsLoading(false);
    }
  }, [username, password, router]);

  return (
    <main className="auth-screen">
      <div className="auth-glow" />
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">✦</span>
          <h1>CFOBuddy</h1>
        </div>
        <p className="auth-subtitle">Welcome back. Sign in to continue.</p>

        <form className="auth-form" onSubmit={(e) => void handleSubmit(e)}>
          <div className="auth-field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your username"
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="auth-field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              autoComplete="current-password"
            />
          </div>

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" className="auth-btn" disabled={isLoading}>
            {isLoading ? <><span className="auth-spinner" /> Signing in...</> : 'Sign in'}
          </button>
        </form>

        <p className="auth-switch">
          Don&apos;t have an account?{' '}
          <Link href="/signup">Create one →</Link>
        </p>
      </div>

      <style jsx>{`
        .auth-screen {
          min-height: 100vh;
          display: grid;
          place-items: center;
          background: #171717;
          position: relative;
          overflow: hidden;
          padding: 2rem;
        }
        .auth-glow {
          position: absolute;
          top: -200px;
          left: 50%;
          transform: translateX(-50%);
          width: 600px;
          height: 600px;
          background: radial-gradient(ellipse, rgba(16,163,127,0.15) 0%, transparent 70%);
          pointer-events: none;
        }
        .auth-card {
          width: min(420px, 100%);
          background: #1e1e1e;
          border: 1px solid #2f2f2f;
          border-radius: 1.5rem;
          padding: 2.5rem 2rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          position: relative;
          z-index: 1;
          box-shadow: 0 24px 80px rgba(0,0,0,0.5);
        }
        .auth-brand {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          justify-content: center;
          margin-bottom: 0.5rem;
        }
        .auth-logo { font-size: 1.5rem; color: #10a37f; }
        .auth-brand h1 { margin: 0; font-size: 1.5rem; font-weight: 700; color: #ececec; }
        .auth-subtitle { text-align: center; color: #666; font-size: 0.9375rem; margin-bottom: 1.25rem; }
        .auth-form { display: flex; flex-direction: column; gap: 1rem; margin-top: 0.5rem; }
        .auth-field { display: flex; flex-direction: column; gap: 0.4rem; }
        .auth-field label { font-size: 0.85rem; color: #aaa; font-weight: 500; }
        .auth-field input {
          width: 100%;
          padding: 0.75rem 1rem;
          border-radius: 0.75rem;
          border: 1px solid #333;
          background: #141414;
          color: #ececec;
          font-size: 0.9375rem;
          font-family: inherit;
          outline: none;
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .auth-field input:focus {
          border-color: #10a37f;
          box-shadow: 0 0 0 3px rgba(16,163,127,0.12);
        }
        .auth-field input::placeholder { color: #444; }
        .auth-error {
          color: #f87171;
          font-size: 0.875rem;
          background: rgba(248,113,113,0.08);
          border: 1px solid rgba(248,113,113,0.2);
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          margin: 0;
        }
        .auth-btn {
          width: 100%;
          margin-top: 0.5rem;
          padding: 0.875rem;
          border: none;
          border-radius: 0.75rem;
          background: #10a37f;
          color: #fff;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.2s, transform 0.15s;
          font-family: inherit;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
        }
        .auth-btn:hover:not(:disabled) { background: #0d8f6e; transform: translateY(-1px); }
        .auth-btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .auth-spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255,255,255,0.3);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
          display: inline-block;
        }
        .auth-switch { text-align: center; font-size: 0.875rem; color: #666; margin-top: 1rem; }
        .auth-switch a { color: #10a37f; font-weight: 500; text-decoration: none; }
        .auth-switch a:hover { color: #0d8f6e; }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </main>
  );
}
