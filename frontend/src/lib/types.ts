export type MessageRole = 'user' | 'assistant';

export interface ChartData {
  type?: string;
  title?: string;
  url?: string;
  file_url?: string;
  chart_url?: string;
  path?: string;
  data?: Record<string, unknown>;
  layout?: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  chart?: ChartData | null;
  timestamp: Date;
  isLoading?: boolean;
}

export interface Thread {
  id: string;
  label: string;
}

export interface UploadedFile {
  name: string;
  type: string;
  size: string;
}

export interface AuthUser {
  username: string;
  auth_type: string;
}

export interface LoginAPIResponse {
  access_token: string;
  token_type: 'bearer';
  username: string;
}

export interface ChatAPIResponse {
  response: string;
  thread_id: string;
  chart?: ChartData | null;
}

export interface ThreadInfo {
  id: string;
  name: string;
}

export interface ThreadsAPIResponse {
  threads: ThreadInfo[];
}

export interface ThreadHistoryMessage {
  role: 'human' | 'ai';
  content: string;
  chart?: ChartData | null;
}

export interface ThreadHistoryAPIResponse {
  thread_id: string;
  messages: ThreadHistoryMessage[];
}

export interface FilesAPIResponse {
  files: UploadedFile[];
}

export interface UploadAPIResponse {
  message: string;
  filename: string;
  thread_id?: string | null;
}

export type StreamTokenCallback = (token: string) => void;
export type StreamCompleteCallback = (full: ChatAPIResponse) => void;
