'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { deleteThread, getThreads } from '../lib/api';
import { createId } from '../lib/id';
import type { ThreadInfo } from '../lib/types';
import { ThreadSkeleton } from './LoadingStates';
import styles from './Sidebar.module.css';

interface Props {
  currentThreadId: string;
  onSelectThread: (id: string) => void;
  userName?: string;
  userRole?: string;
  isOpen?: boolean;
  onToggle?: () => void;
  onLogout?: () => void;
  onThreadsLoaded?: (ids: string[]) => void;
}

export default function Sidebar({
  currentThreadId,
  onSelectThread,
  userName = 'Authenticated User',
  userRole = 'JWT Session',
  isOpen = true,
  onToggle,
  onLogout,
  onThreadsLoaded,
}: Props) {
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const [menuOpenThreadId, setMenuOpenThreadId] = useState<string | null>(null);
  const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string>('');

  useEffect(() => {
    async function loadThreads() {
      try {
        const res = await getThreads();
        setThreads(res.threads);
        onThreadsLoaded?.(res.threads.map((t) => t.id));
      } catch (err) {
        console.error('Failed to load threads', err);
        setThreads([{ id: 'main', name: 'Main Analysis' }]);
      } finally {
        setIsLoading(false);
      }
    }
    loadThreads();
  }, []);

  const handleDelete = useCallback(
    async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setMenuOpenThreadId(null);
      try {
        await deleteThread(threadId);
        setThreads((prev) => prev.filter((t) => t.id !== threadId));
        if (threadId === currentThreadId) {
          onSelectThread(createId());
        }
      } catch (err) {
        console.error('Failed to delete thread', err);
      }
    },
    [currentThreadId, onSelectThread],
  );

  const startRename = (threadId: string, currentName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpenThreadId(null);
    setEditingThreadId(threadId);
    setEditingName(currentName);
  };

  const handleRenameSubmit = async (threadId: string) => {
    if (!editingName.trim()) {
      setEditingThreadId(null);
      return;
    }
    try {
      await import('../lib/api').then(api => api.renameThread(threadId, editingName.trim()));
      setThreads((prev) => prev.map((t) => (t.id === threadId ? { ...t, name: editingName.trim() } : t)));
    } catch (err) {
      console.error('Failed to rename thread', err);
    } finally {
      setEditingThreadId(null);
    }
  };

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setMenuOpenThreadId(null);
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  return (
    <aside className={`${styles.sidebar} ${isOpen ? styles.sidebarOpen : styles.sidebarClosed}`}>
      {/* Top bar: toggle + new chat */}
      <div className={styles.topBar}>
        <button className={styles.toggleBtn} onClick={onToggle} aria-label="Close sidebar">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M9 3v18" />
          </svg>
        </button>
        <button
          className={styles.newChatBtn}
          onClick={() => {
            const newId = createId();
            onSelectThread(newId);
            setThreads(prev => [{id: newId, name: 'New Chat'}, ...prev]);
          }}
          title="New chat"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>

      {/* Threads list */}
      <div className={styles.threadsList}>
        {isLoading ? (
          <ThreadSkeleton />
        ) : (
          threads.map((thread) => (
            <div key={thread.id} className={styles.threadItemWrapper}>
              <div
                onClick={() => onSelectThread(thread.id)}
                className={`${styles.threadItem} ${thread.id === currentThreadId ? styles.threadActive : ''}`}
                role="button"
                tabIndex={0}
              >
                <svg className={styles.threadIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                </svg>
                
                {editingThreadId === thread.id ? (
                  <input
                    type="text"
                    className={styles.renameInput}
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void handleRenameSubmit(thread.id);
                      if (e.key === 'Escape') setEditingThreadId(null);
                    }}
                    onBlur={() => void handleRenameSubmit(thread.id)}
                    autoFocus
                  />
                ) : (
                  <span className={styles.threadName}>
                    {thread.name}
                  </span>
                )}

                {!editingThreadId && (
                  <span
                    className={`${styles.menuBtn} ${menuOpenThreadId === thread.id ? styles.menuBtnActive : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      if (e.nativeEvent && e.nativeEvent.stopImmediatePropagation) {
                        e.nativeEvent.stopImmediatePropagation();
                      }
                      setMenuOpenThreadId(menuOpenThreadId === thread.id ? null : thread.id);
                    }}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="1" />
                      <circle cx="12" cy="5" r="1" />
                      <circle cx="12" cy="19" r="1" />
                    </svg>
                  </span>
                )}
              </div>

              {menuOpenThreadId === thread.id && (
                <div className={styles.dropdownMenu} onClick={(e) => e.stopPropagation()}>
                  <button className={styles.dropdownItem} onClick={(e) => startRename(thread.id, thread.name, e)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    Rename
                  </button>
                  <button className={`${styles.dropdownItem} ${styles.dropdownItemDelete}`} onClick={(e) => void handleDelete(thread.id, e)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    Delete
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Bottom section – user + logout */}
      <div className={styles.bottomSection}>
        <a
          href="http://localhost:8000/admin/observability"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.navItem}
          title="Open Observability & Tracing Dashboard"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18" />
            <path d="M18 17l-6-6-4 4-5-5" />
          </svg>
          <span>Observability</span>
        </a>

        <Link href="/" className={styles.navItem}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
          </svg>
          <span>Home</span>
        </Link>

        <div className={styles.userProfile}>
          <div className={styles.avatar}>{userName.slice(0, 2).toUpperCase()}</div>
          <div className={styles.userInfo}>
            <p className={styles.userName}>{userName}</p>
            <p className={styles.userRole}>{userRole}</p>
          </div>
          {onLogout && (
            <button className={styles.logoutBtn} onClick={onLogout} title="Sign out">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
