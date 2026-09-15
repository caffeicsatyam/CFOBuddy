'use client';

import { memo, useEffect, useRef, useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props {
  content: string;
  isStreaming: boolean;
}

/**
 * StreamingText renders AI response content with a smooth token-by-token
 * typing effect while streaming, then switches to full Markdown rendering
 * once the stream completes.
 *
 * During streaming:
 *   - Renders raw text (no Markdown parsing) to avoid layout jank
 *   - Shows a blinking cursor at the end
 *   - New tokens fade in smoothly
 *
 * After streaming:
 *   - Renders full Markdown with remark-gfm for tables, lists, etc.
 */
function StreamingText({ content, isStreaming }: Props) {
  const [showMarkdown, setShowMarkdown] = useState(!isStreaming);
  const prevLenRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // When streaming finishes, transition from raw text to Markdown
  useEffect(() => {
    if (!isStreaming && content.length > 0) {
      // Small delay to avoid a flash when the last token arrives
      const timer = setTimeout(() => setShowMarkdown(true), 60);
      return () => clearTimeout(timer);
    }
    if (isStreaming) {
      setShowMarkdown(false);
    }
  }, [isStreaming, content.length]);

  // Track the previously rendered length so we can highlight new tokens
  useEffect(() => {
    prevLenRef.current = content.length;
  }, [content]);

  if (!content && isStreaming) {
    return <span className="streaming-cursor" />;
  }

  // After stream ends, render full Markdown
  if (showMarkdown && !isStreaming) {
    return <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>;
  }

  // During streaming: render raw text with cursor
  // Split into already-rendered portion and new tokens for a fade-in effect
  const oldLen = prevLenRef.current;
  const oldText = content.slice(0, oldLen);
  const newText = content.slice(oldLen);

  return (
    <div ref={containerRef} className="streaming-text-container">
      <span className="streaming-rendered">{oldText}</span>
      {newText && <span className="streaming-new">{newText}</span>}
      <span className="streaming-cursor" />
    </div>
  );
}

export default memo(StreamingText);
