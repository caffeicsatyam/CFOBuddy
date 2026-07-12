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
  }, [onThreadsLoaded]);

  const handleDelete = useCallback(
    async (threadId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await deleteThread(threadId);
        setThreads((prev) => prev.filter((t) => t.id !== threadId));
        // If the deleted thread was selected, switch to a new chat
        if (threadId === currentThreadId) {
          onSelectThread(createId());
        }
      } catch (err) {
        console.error('Failed to delete thread', err);
      }
    },
    [currentThreadId, onSelectThread],
  );

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
          onClick={() => onSelectThread(createId())}
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
            <button
              key={thread.id}
              onClick={() => onSelectThread(thread.id)}
              className={`${styles.threadItem} ${thread.id === currentThreadId ? styles.threadActive : ''}`}
            >
              <svg className={styles.threadIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
              <span className={styles.threadName}>
                {thread.name}
              </span>
              <span
                className={styles.deleteBtn}
                role="button"
                tabIndex={0}
                title="Delete thread"
                onClick={(e) => void handleDelete(thread.id, e)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleDelete(thread.id, e as unknown as React.MouseEvent);
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 6h18" />
                  <path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                </svg>
              </span>
            </button>
          ))
        )}
      </div>

      {/* Bottom section – user + logout */}
      <div className={styles.bottomSection}>
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
