'use client';

import { useRef, useEffect, KeyboardEvent, ChangeEvent } from 'react';
import { Spinner } from './LoadingStates';
import styles from './ChatInput.module.css';

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onFileSelect?: (file: File) => void | Promise<void>;
  disabled?: boolean;
  loading?: boolean;
  uploadLoading?: boolean;
  placeholder?: string;
}

export default function ChatInput({
  value,
  onChange,
  onSend,
  onFileSelect,
  disabled = false,
  loading = false,
  uploadLoading = false,
  placeholder = 'Message CFOBuddy…',
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && !loading && value.trim()) onSend();
    }
  };

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !onFileSelect) return;

    try {
      await onFileSelect(file);
    } finally {
      event.target.value = '';
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.inputContainer}>
        <input
          ref={fileInputRef}
          type="file"
          className={styles.hiddenInput}
          accept=".csv,.pdf,.xlsx,.xls,.docx"
          onChange={handleFileChange}
          disabled={disabled || uploadLoading}
        />
        <button
          type="button"
          className={styles.uploadBtn}
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploadLoading}
          aria-label="Upload financial file"
          title="Upload CSV, PDF, XLSX, XLS, or DOCX"
        >
          {uploadLoading ? (
            <Spinner size={16} />
          ) : (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
            </svg>
          )}
        </button>
        <textarea
          ref={textareaRef}
          id="chat-input"
          className={styles.textarea}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled || loading}
          rows={1}
          aria-label="Chat message"
        />
        <button
          id="chat-send-btn"
          className={styles.sendBtn}
          onClick={onSend}
          disabled={disabled || loading || !value.trim()}
          aria-label="Send message"
        >
          {loading ? (
            <Spinner size={16} />
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94l18.04-8.01a.75.75 0 000-1.36L3.478 2.405z" />
            </svg>
          )}
        </button>
      </div>
      <p className={styles.hint}>
        CFOBuddy can make mistakes. Verify important financial data.
      </p>
    </div>
  );
}
