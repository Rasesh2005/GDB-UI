/**
 * jest.setup.ts — Global Jest setup for frontend tests.
 *
 * Runs before every test file via the `setupFilesAfterFramework` Jest config key.
 *
 * Provides:
 *  - @testing-library/jest-dom matchers (toBeInTheDocument, toBeDisabled, …)
 *  - fetch mock (so tests don't make real network requests)
 *  - WebSocket mock (so contexts that open WS in useEffect don't fail)
 *  - window.location.reload mock (AuthContext calls it on login/logout)
 */

import '@testing-library/jest-dom';

// ---------------------------------------------------------------------------
// Mock window.location for JSDOM 30
// ---------------------------------------------------------------------------
// window.location is patched by the custom test environment (jest.environment.cjs)
// before the test sandbox is active. Here we only suppress the JSDOM navigation
// warning that leaks through when location methods are called directly.
const origConsoleError = console.error.bind(console);
console.error = (...args: any[]) => {
  const firstArg = args[0];
  // Suppress JSDOM navigation noise — arrives as both string and Error object
  if (
    (typeof firstArg === 'string' && firstArg.includes('Not implemented')) ||
    (firstArg instanceof Error && firstArg.message?.includes('Not implemented'))
  ) {
    return;
  }
  origConsoleError(...args);
};

// ---------------------------------------------------------------------------
// Mock WebSocket globally
// ---------------------------------------------------------------------------
// DebugContext opens a WebSocket in useEffect. We expose a mock so individual
// tests can inspect sent messages.
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e: Event) => void) | null = null;

  sentMessages: string[] = [];

  constructor(public url: string) {
    // Simulate async connection
    setTimeout(() => this.onopen?.(), 0);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  /** Helper: simulate receiving a message from the server. */
  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

(global as any).WebSocket = MockWebSocket;

// ---------------------------------------------------------------------------
// Default fetch mock — returns 401 (unauthenticated) by default.
// Individual tests override this with jest.fn() as needed.
// ---------------------------------------------------------------------------
global.fetch = jest.fn().mockResolvedValue({
  ok: false,
  status: 401,
  json: () => Promise.resolve({ detail: 'Not logged in' }),
});

// Reset all mocks after every test to prevent cross-test pollution.
afterEach(() => {
  jest.resetAllMocks();
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: false,
    status: 401,
    json: () => Promise.resolve({ detail: 'Not logged in' }),
  });
});
