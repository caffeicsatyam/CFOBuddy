'use client';

import { useCallback, useEffect, useState } from 'react';

import ChatArea from '@/components/ChatArea';
import ChatInput from '@/components/ChatInput';
import Sidebar from '@/components/Sidebar';
import {
  clearAuthToken,
  getCurrentUser,
  getThreadHistory,
  hasAuthToken,
  login,
  register,
  sendMessageStream,
  uploadFile,
} from '@/lib/api';
import { createId } from '@/lib/id';
import type { AuthUser, Message } from '@/lib/types';

export default function Dashboard() {
  const [currentThreadId, setCurrentThreadId] = useState<string>(() => createId());
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  // Track which thread IDs are known to exist on the backend
  const [knownThreadIds, setKnownThreadIds] = useState<Set<string>>(new Set());

  const loadThread = useCallback(async (threadId: string, forceLoad = false) => {
    if (!user) {
      setMessages([]);
      return;
    }

    // Skip fetching history for brand-new threads not yet persisted on the backend
    if (!forceLoad && !knownThreadIds.has(threadId)) {
      setMessages([]);
      return;
    }

    try {
      const history = await getThreadHistory(threadId);
      const mappedMessages: Message[] = history.messages.map((message, index) => ({
        id: `${threadId}-${index}-${createId()}`,
        role: message.role === 'human' ? 'user' : 'assistant',
        content: message.content,
        chart: message.chart,
        timestamp: new Date(),
      }));
      setMessages(mappedMessages);
    } catch (error) {
      console.error(`Failed to load history for thread ${threadId}`, error);
      setMessages([
        {
          id: createId(),
          role: 'assistant',
          content:
            error instanceof Error
              ? `Error loading thread history: ${error.message}`
              : 'Error loading thread history.',
          timestamp: new Date(),
        },
      ]);
    }
  }, [user, knownThreadIds]);

  useEffect(() => {
    if (user) {
      void loadThread(currentThreadId);
    }
  }, [currentThreadId, loadThread, user]);

  useEffect(() => {
    async function bootstrapAuth() {
      if (!hasAuthToken()) {
        setAuthLoading(false);
        return;
      }

      try {
        const me = await getCurrentUser();
        setUser(me);
      } catch (error) {
        console.error('Failed to restore auth session', error);
        clearAuthToken();
      } finally {
        setAuthLoading(false);
      }
    }

    void bootstrapAuth();
  }, []);

  const handleLogin = useCallback(async () => {
    if (!username.trim() || !password.trim()) {
      setAuthError('Enter both username and password.');
      return;
    }

    setIsLoggingIn(true);
    setAuthError(null);

    try {
      await login(username.trim(), password);
      const me = await getCurrentUser();
      setUser(me);
      setPassword('');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Login failed');
    } finally {
      setIsLoggingIn(false);
      setAuthLoading(false);
    }
  }, [password, username]);

  const handleRegister = useCallback(async () => {
    if (!username.trim() || !password.trim()) {
      setAuthError('Enter both username and password.');
      return;
    }

    setIsLoggingIn(true);
    setAuthError(null);

    try {
      await register(username.trim(), password);
      // Auto-login after successful registration
      await login(username.trim(), password);
      const me = await getCurrentUser();
      setUser(me);
      setPassword('');
      setIsRegisterMode(false);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Registration failed');
    } finally {
      setIsLoggingIn(false);
      setAuthLoading(false);
    }
  }, [password, username]);

  const handleLogout = useCallback(() => {
    clearAuthToken();
    setUser(null);
    setMessages([]);
    setCurrentThreadId('main');
    setAuthError(null);
  }, []);

  const handleFileUpload = useCallback(async (file: File) => {
    const uploadMessageId = createId();
    const assistantId = createId();

    setMessages((prev) => [
      ...prev,
      {
        id: uploadMessageId,
        role: 'user',
        content: `Upload file: ${file.name}`,
        timestamp: new Date(),
      },
      {
        id: assistantId,
        role: 'assistant',
        content: `Uploading ${file.name}...`,
        timestamp: new Date(),
        isLoading: true,
      },
    ]);
    setIsUploadingFile(true);

    const updateUploadStatus = (content: string, isLoading = false) => {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantId
            ? { ...message, content, isLoading }
            : message,
        ),
      );
    };

    try {
      const uploadResponse = await uploadFile(file, currentThreadId);
      updateUploadStatus(
        `${uploadResponse.message} I am processing it in the background, so you can keep chatting while embeddings are generated.`,
      );
      if (uploadResponse.thread_id) {
        setKnownThreadIds((prev) => new Set([...prev, uploadResponse.thread_id as string]));
      }
    } catch (error) {
      updateUploadStatus(
        `Upload failed: ${error instanceof Error ? error.message : 'Unable to upload file.'}`,
      );
    } finally {
      setIsUploadingFile(false);
    }
  }, [currentThreadId]);

  const handleSend = useCallback(async () => {
    if (!inputVal.trim()) return;

    const userText = inputVal.trim();
    setInputVal('');

    const userMsg: Message = {
      id: createId(),
      role: 'user',
      content: userText,
      timestamp: new Date(),
    };

    const assistantId = createId();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsTyping(true);

    try {
      await sendMessageStream(
        userText,
        currentThreadId,
        (token) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, content: `${message.content}${token}` }
                : message,
            ),
          );
        },
        (res) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: res.response || message.content,
                    chart: res.chart,
                    isLoading: false,
                  }
                : message,
            ),
          );
          // Mark thread as known on the backend so history can be fetched next time
          setKnownThreadIds((prev) => new Set([...prev, res.thread_id]));
          setCurrentThreadId(res.thread_id);
        },
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: `Error: ${
                  error instanceof Error ? error.message : 'Failed to connect to AI'
                }`,
                isLoading: false,
              }
            : message,
        ),
      );
    } finally {
      setIsTyping(false);
    }
  }, [currentThreadId, inputVal]);

  const handleSuggestionClick = useCallback(async (suggestion: string) => {
    setInputVal('');
    const userMsg: Message = {
      id: createId(),
      role: 'user',
      content: suggestion,
      timestamp: new Date(),
    };

    const assistantId = createId();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsTyping(true);

    try {
      await sendMessageStream(
        suggestion,
        currentThreadId,
        (token) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? { ...message, content: `${message.content}${token}` }
                : message,
            ),
          );
        },
        (res) => {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    content: res.response || message.content,
                    chart: res.chart,
                    isLoading: false,
                  }
                : message,
            ),
          );
          setKnownThreadIds((prev) => new Set([...prev, res.thread_id]));
          setCurrentThreadId(res.thread_id);
        },
      );
    } catch (error) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                content: `Error: ${error instanceof Error ? error.message : 'Failed to connect to AI'}`,
                isLoading: false,
              }
            : message,
        ),
      );
    } finally {
      setIsTyping(false);
    }
  }, [currentThreadId]);

  /* ── Loading gate ──────────────────────────────────────── */
  if (authLoading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-spinner" />
        <p>Restoring your session…</p>
      </div>
    );
  }

  /* ── Login / Register screen ─────────────────────────────── */
  if (!user) {
    const submitHandler = isRegisterMode ? handleRegister : handleLogin;
    return (
      <main className="login-screen">
        <section className="login-card">
          <div className="login-brand">
            <span className="login-logo">✦</span>
            <h1>CFOBuddy</h1>
          </div>
          <p className="login-subtitle">
            {isRegisterMode
              ? 'Create a new account'
              : 'Sign in to your financial assistant'}
          </p>

          <div className="login-fields">
            <label className="login-label">
              <span>Username</span>
              <input
                className="login-input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                placeholder="Enter username"
              />
            </label>

            <label className="login-label">
              <span>Password</span>
              <input
                className="login-input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !isLoggingIn) {
                    void submitHandler();
                  }
                }}
                autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                placeholder="Enter password"
              />
            </label>
          </div>

          {authError ? (
            <p className="login-error">{authError}</p>
          ) : null}

          <button
            className="login-btn"
            onClick={() => void submitHandler()}
            disabled={isLoggingIn}
          >
            {isLoggingIn ? (
              <span className="login-btn-loading">
                <span className="login-spinner" />
                {isRegisterMode ? 'Creating account…' : 'Signing in…'}
              </span>
            ) : isRegisterMode ? 'Create Account' : 'Continue'}
          </button>

          <p className="login-toggle">
            {isRegisterMode ? (
              <>
                Already have an account?{' '}
                <button
                  className="login-toggle-btn"
                  onClick={() => { setIsRegisterMode(false); setAuthError(null); }}
                >
                  Sign In
                </button>
              </>
            ) : (
              <>
                Don&apos;t have an account?{' '}
                <button
                  className="login-toggle-btn"
                  onClick={() => { setIsRegisterMode(true); setAuthError(null); setUsername(''); }}
                >
                  Sign Up
                </button>
              </>
            )}
          </p>

          <p className="login-footnote">
            Secured with JWT authentication
          </p>
        </section>

        <style jsx>{`
          .login-screen {
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 2rem;
            background: #171717;
          }
          .login-card {
            width: min(400px, 100%);
            padding: 2.5rem 2rem;
            border-radius: 1.25rem;
            background: #2f2f2f;
            border: 1px solid #444;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
          }
          .login-brand {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            justify-content: center;
            margin-bottom: 0.25rem;
          }
          .login-logo {
            font-size: 1.5rem;
            color: #10a37f;
          }
          .login-brand h1 {
            margin: 0;
            font-size: 1.5rem;
            font-weight: 700;
          }
          .login-subtitle {
            text-align: center;
            color: #999;
            font-size: 0.9375rem;
            margin-bottom: 1.25rem;
          }
          .login-fields {
            display: flex;
            flex-direction: column;
            gap: 1rem;
          }
          .login-label {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            font-size: 0.875rem;
            color: #ccc;
          }
          .login-input {
            width: 100%;
            padding: 0.75rem 1rem;
            border-radius: 0.625rem;
            border: 1px solid #555;
            background: #212121;
            color: #ececec;
            font-size: 0.9375rem;
            font-family: inherit;
            outline: none;
            transition: border-color 0.2s;
          }
          .login-input:focus {
            border-color: #10a37f;
          }
          .login-input::placeholder {
            color: #666;
          }
          .login-error {
            color: #ef4444;
            font-size: 0.875rem;
            margin: 0.25rem 0;
          }
          .login-btn {
            width: 100%;
            margin-top: 1rem;
            padding: 0.8rem;
            border: none;
            border-radius: 0.625rem;
            background: #10a37f;
            color: #fff;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            font-family: inherit;
          }
          .login-btn:hover:not(:disabled) {
            background: #1a8a6a;
          }
          .login-btn:disabled {
            opacity: 0.7;
            cursor: not-allowed;
          }
          .login-btn-loading {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
          }
          .login-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: #fff;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
          }
          .login-toggle {
            text-align: center;
            font-size: 0.875rem;
            color: #999;
            margin-top: 0.75rem;
          }
          .login-toggle-btn {
            background: none;
            border: none;
            color: #10a37f;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 600;
            font-family: inherit;
            text-decoration: underline;
            padding: 0;
          }
          .login-toggle-btn:hover {
            color: #1a8a6a;
          }
          .login-footnote {
            text-align: center;
            font-size: 0.75rem;
            color: #666;
            margin-top: 1rem;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </main>
    );
  }

  /* ── Main chat UI ──────────────────────────────────────── */
  return (
    <div className="dashboard-layout">
      <Sidebar
        currentThreadId={currentThreadId}
        onSelectThread={(id) => setCurrentThreadId(id)}
        userName={user.username}
        userRole={user.auth_type === 'jwt' ? 'JWT Session' : 'Legacy API Key'}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((s) => !s)}
        onLogout={handleLogout}
        onThreadsLoaded={(ids) => setKnownThreadIds(new Set(ids))}
      />

      <main className="chat-main">
        {/* Hamburger toggle when sidebar is closed */}
        {!sidebarOpen && (
          <button
            className="sidebar-toggle-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M9 3v18" />
            </svg>
          </button>
        )}

        <div className="chat-messages-area">
          <ChatArea
            messages={messages}
            isTyping={isTyping}
            onSuggestionClick={handleSuggestionClick}
          />
        </div>

        <div className="chat-input-area">
          <ChatInput
            value={inputVal}
            onChange={setInputVal}
            onSend={handleSend}
            loading={isTyping}
            uploadLoading={isUploadingFile}
            onFileSelect={handleFileUpload}
          />
        </div>
      </main>

      <style jsx>{`
        .dashboard-layout {
          display: flex;
          height: 100vh;
          overflow: hidden;
          background: var(--surface);
        }
        .chat-main {
          flex: 1;
          display: flex;
          flex-direction: column;
          position: relative;
          min-width: 0;
        }
        .sidebar-toggle-btn {
          position: absolute;
          top: 0.75rem;
          left: 0.75rem;
          z-index: 20;
          width: 36px;
          height: 36px;
          border: none;
          background: transparent;
          color: var(--on-surface-variant);
          border-radius: var(--radius);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background var(--transition), color var(--transition);
        }
        .sidebar-toggle-btn:hover {
          background: var(--surface-container);
          color: var(--on-surface);
        }
        .chat-messages-area {
          flex: 1;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }
        .chat-input-area {
          padding: 0 1rem 1.5rem;
          background: transparent;
        }
        .auth-loading-screen {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          background: var(--surface);
          color: var(--on-surface-variant);
        }
        .auth-loading-spinner {
          width: 24px;
          height: 24px;
          border: 2px solid var(--outline-variant);
          border-top-color: var(--on-surface-variant);
          border-radius: 50%;
          animation: spin 0.6s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
