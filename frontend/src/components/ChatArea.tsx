'use client';

import Image from 'next/image';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

import { getApiBaseUrl } from '../lib/api';
import type { Message } from '../lib/types';
import { TypingIndicator } from './LoadingStates';
import styles from './ChatArea.module.css';

interface Props {
  messages: Message[];
  isTyping: boolean;
  onSuggestionClick?: (suggestion: string) => void;
}

interface ChartPreview {
  src: string;
  title: string;
  isHtml: boolean;
}

function extractChartPath(message: Message): string | null {
  const chartCandidateKeys = ['url', 'file_url', 'chart_url', 'path'];

  if (message.chart && typeof message.chart === 'object') {
    for (const key of chartCandidateKeys) {
      const value = (message.chart as Record<string, unknown>)[key];
      if (typeof value === 'string' && value.length > 0) {
        return value;
      }
    }
  }

  // Match both .html and .png chart URLs from message content
  const match = message.content.match(/\/charts\/[^\s`)"']+\.(?:html|png)/);
  return match ? match[0] : null;
}

function resolveChartPreview(message: Message): ChartPreview | null {
  const chartPath = extractChartPath(message);
  if (!chartPath) {
    return null;
  }

  const title =
    (message.chart &&
      typeof message.chart === 'object' &&
      typeof (message.chart as Record<string, unknown>).title === 'string' &&
      ((message.chart as Record<string, string>).title || '').trim()) ||
    'Generated chart';

  const normalizedPath = chartPath.startsWith('http')
    ? chartPath
    : `${getApiBaseUrl()}${chartPath.startsWith('/') ? '' : '/'}${chartPath}`;

  return {
    src: normalizedPath,
    title,
    isHtml: chartPath.endsWith('.html'),
  };
}

const SUGGESTION_CHIPS = [
  { icon: '', label: 'Analyze P&L', prompt: 'Analyze my profit and loss statement and highlight key trends' },
  { icon: '', label: 'Revenue trends', prompt: 'Show me a chart of revenue trends over the last 12 months' },
  { icon: '', label: 'Cash flow health', prompt: 'What is the current state of my cash flow and runway?' },
  { icon: '', label: 'Quick ratios', prompt: 'Calculate key financial ratios from the uploaded data' },
];

export default function ChatArea({ messages, isTyping, onSuggestionClick }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [activeChart, setActiveChart] = useState<ChartPreview | null>(null);
  const hasStreamingMessage = messages.some((message) => message.isLoading);

  const openChartFromKeyboard = (
    event: KeyboardEvent<HTMLDivElement>,
    chartPreview: ChartPreview,
  ) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setActiveChart(chartPreview);
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const previews = useMemo(
    () =>
      new Map(
        messages.map((message) => [message.id, resolveChartPreview(message)])
      ),
    [messages]
  );

  return (
    <div className={styles.chatContainer}>
      {messages.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyLogo}>✦</div>
          <h1 className={styles.emptyTitle}>What can I help with?</h1>
          <p className={styles.emptySubtitle}>
            Ask me anything about your financial data — from P&L analysis to cash flow forecasting.
          </p>

          <div className={styles.suggestions}>
            {SUGGESTION_CHIPS.map((chip) => (
              <button
                key={chip.label}
                className={styles.suggestionChip}
                onClick={() => onSuggestionClick?.(chip.prompt)}
              >
                <span className={styles.chipIcon}>{chip.icon}</span>
                <span className={styles.chipLabel}>{chip.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className={styles.messageList}>
          {messages.map((msg) => {
            const chartPreview = previews.get(msg.id) ?? null;

            return (
              <div
                key={msg.id}
                className={`${styles.messageRow} ${
                  msg.role === 'user' ? styles.rowUser : styles.rowAi
                }`}
              >
                <div className={styles.messageInner}>
                  {msg.role === 'assistant' && (
                    <div className={styles.avatarAi}>
                      <span>✦</span>
                    </div>
                  )}

                  <div
                    className={`${styles.messageBubble} ${
                      msg.role === 'user' ? styles.bubbleUser : styles.bubbleAi
                    }`}
                  >
                    <div className={styles.content}>
                      {msg.content.split('\n').map((line, i) => (
                        <span key={i}>
                          {line}
                          <br />
                        </span>
                      ))}
                      {msg.isLoading && msg.role === 'assistant' && (
                        <span className="streaming-cursor"></span>
                      )}
                    </div>

                    {chartPreview && (
                      <div
                        role="button"
                        tabIndex={0}
                        className={styles.chartCard}
                        onClick={() => setActiveChart(chartPreview)}
                        onKeyDown={(event) => openChartFromKeyboard(event, chartPreview)}
                      >
                        <div className={styles.chartCardHeader}>
                          <div className={styles.chartIcon}></div>
                          <span className={styles.chartLabel}>{chartPreview.title}</span>
                        </div>
                        {chartPreview.isHtml ? (
                          <iframe
                            src={chartPreview.src}
                            title={chartPreview.title}
                            className={styles.chartIframe}
                            style={{
                              width: '100%',
                              height: '300px',
                              border: 'none',
                              borderRadius: '8px',
                              pointerEvents: 'none',
                            }}
                          />
                        ) : (
                          <Image
                            src={chartPreview.src}
                            alt={chartPreview.title}
                            className={styles.chartImage}
                            width={960}
                            height={540}
                            unoptimized
                          />
                        )}
                        <span className={styles.chartHint}>Click to expand</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {isTyping && !hasStreamingMessage && (
            <div className={`${styles.messageRow} ${styles.rowAi}`}>
              <div className={styles.messageInner}>
                <TypingIndicator />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      )}

      {activeChart && (
        <div
          role="button"
          tabIndex={-1}
          className={styles.chartModal}
          onClick={() => setActiveChart(null)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              setActiveChart(null);
            }
          }}
        >
          <div
            className={styles.chartModalContent}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.chartModalHeader}>
              <h3>{activeChart.title}</h3>
              <button
                type="button"
                className={styles.chartClose}
                onClick={() => setActiveChart(null)}
              >
                ×
              </button>
            </div>
            {activeChart.isHtml ? (
              <iframe
                src={activeChart.src}
                title={activeChart.title}
                className={styles.chartModalIframe}
                style={{
                  width: '100%',
                  height: '70vh',
                  border: 'none',
                  borderRadius: '8px',
                }}
              />
            ) : (
              <Image
                src={activeChart.src}
                alt={activeChart.title}
                className={styles.chartModalImage}
                width={1400}
                height={900}
                unoptimized
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
