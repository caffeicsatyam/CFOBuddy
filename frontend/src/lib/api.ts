import type {
  AuthUser,
  ChatAPIResponse,
  FilesAPIResponse,
  LoginAPIResponse,
  StreamCompleteCallback,
  StreamTokenCallback,
  ThreadHistoryAPIResponse,
  ThreadsAPIResponse,
  UploadAPIResponse,
} from './types';

const CONFIGURED_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';
const LEGACY_API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? '';
const AUTH_TOKEN_KEY = 'cfobuddy.auth.token';

export function getApiBaseUrl(): string {
  // Use Next.js rewrites to proxy API requests to the backend.
  // This bypasses Windows Firewall issues when accessing from LAN,
  // and prevents IPv6 vs IPv4 resolution issues on localhost.
  return '/api';
}

function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function saveAuthToken(token: string): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
}

export function clearAuthToken(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

export function hasAuthToken(): boolean {
  return Boolean(getStoredToken());
}

async function parseError(res: Response, fallback: string): Promise<never> {
  try {
    const data = (await res.json()) as { detail?: string; error?: string };
    throw new Error(data.detail ?? data.error ?? fallback);
  } catch (error) {
    if (error instanceof Error && error.message) throw error;
    throw new Error(fallback);
  }
}

function headers(extra: Record<string, string> = {}): HeadersInit {
  const token = getStoredToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  };
}

export async function login(username: string, password: string): Promise<LoginAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const form = new URLSearchParams();
  form.set('username', username);
  form.set('password', password);
  const res = await fetch(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  });
  if (!res.ok) await parseError(res, 'Login failed');
  const data = (await res.json()) as LoginAPIResponse;
  saveAuthToken(data.access_token);
  return data;
}

export async function register(username: string, password: string, fullName = ''): Promise<LoginAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, full_name: fullName }),
  });
  if (!res.ok) await parseError(res, 'Registration failed');
  const data = (await res.json()) as LoginAPIResponse;
  saveAuthToken(data.access_token);
  return data;
}

export async function getCurrentUser(): Promise<AuthUser> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/auth/me`, { headers: headers() });
  if (!res.ok) {
    if (res.status === 401) clearAuthToken();
    await parseError(res, 'Unable to load current user');
  }
  return res.json() as Promise<AuthUser>;
}

export async function sendMessage(message: string, threadId: string): Promise<ChatAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/chat`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) await parseError(res, 'Chat request failed');
  return res.json() as Promise<ChatAPIResponse>;
}

export async function sendMessageStream(
  message: string,
  threadId: string,
  onToken: StreamTokenCallback,
  onComplete: StreamCompleteCallback
): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/chat/stream`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  if (!res.ok) await parseError(res, 'Chat request failed');
  if (!res.body) throw new Error('Streaming response is unavailable');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';
  let completed = false;

  const handleEvent = (block: string) => {
    const lines = block.split('\n');
    const eventLine = lines.find((line) => line.startsWith('event:'));
    const dataLines = lines.filter((line) => line.startsWith('data:'));
    const event = eventLine?.slice('event:'.length).trim() ?? 'message';
    const data = dataLines.map((line) => line.slice('data:'.length).trim()).join('\n');
    if (!data) return;
    if (event === 'token') {
      const parsed = JSON.parse(data) as { token?: string };
      if (parsed.token) { accumulated += parsed.token; onToken(parsed.token); }
      return;
    }
    if (event === 'done') { completed = true; onComplete(JSON.parse(data) as ChatAPIResponse); return; }
    if (event === 'error') {
      const parsed = JSON.parse(data) as { detail?: string };
      throw new Error(parsed.detail ?? 'Streaming chat request failed');
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) handleEvent(block.trimEnd());
  }
  if (buffer.trim()) handleEvent(buffer.trimEnd());
  if (!completed) onComplete({ response: accumulated, thread_id: threadId, chart: null });
}

export async function getThreads(): Promise<ThreadsAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/threads`, { headers: headers() });
  if (!res.ok) await parseError(res, 'Unable to load threads');
  return res.json() as Promise<ThreadsAPIResponse>;
}

export async function deleteThread(threadId: string): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/threads/${threadId}`, {
    method: 'DELETE',
    headers: headers(),
  });
  if (!res.ok) await parseError(res, 'Failed to delete thread');
}

export async function renameThread(threadId: string, newName: string): Promise<void> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/threads/${threadId}/rename`, {
    method: 'PUT',
    headers: headers(),
    body: JSON.stringify({ name: newName }),
  });
  if (!res.ok) await parseError(res, 'Failed to rename thread');
}

export async function getThreadHistory(threadId: string): Promise<ThreadHistoryAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/threads/${threadId}/history`, { headers: headers() });
  if (res.status === 404) return { thread_id: threadId, messages: [] };
  if (!res.ok) await parseError(res, 'Unable to load thread history');
  return res.json() as Promise<ThreadHistoryAPIResponse>;
}

export async function getFiles(): Promise<FilesAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/files`, { headers: headers() });
  if (!res.ok) await parseError(res, 'Unable to load files');
  return res.json() as Promise<FilesAPIResponse>;
}

export async function uploadFile(file: File): Promise<UploadAPIResponse> {
  const baseUrl = getApiBaseUrl();
  const form = new FormData();
  form.append('file', file);
  const token = getStoredToken();
  const res = await fetch(`${baseUrl}/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) await parseError(res, 'Upload failed');
  return res.json() as Promise<UploadAPIResponse>;
}

export async function getIndexingStatus(): Promise<{ status: string; message: string }> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}/indexing_status`, { headers: headers() });
  if (!res.ok) await parseError(res, 'Unable to load indexing status');
  return res.json() as Promise<{ status: string; message: string }>;
}
