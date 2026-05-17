/**
 * AuthContext.test.jsx — Section 5.1
 *
 * Tests the useAuth hook in isolation.
 *
 * WHY: AuthContext is used by both AuthModal and ControlPanel.
 *      If login() throws instead of returning false, or if user state
 *      isn't cleared on logout, the UI gets stuck.
 */

import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../frontend/src/contexts/AuthContext';

const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

test('initial user is null while loading (before /api/me resolves)', () => {
  /**
   * WHY: On first render, user should be null, not yet resolved.
   *      If this is non-null by default, the "Login" button won't show.
   */
  global.fetch = jest.fn(() => new Promise(() => {})); // Never resolves (simulates in-flight)

  const { result } = renderHook(() => useAuth(), { wrapper });
  expect(result.current.user).toBe(null);
});

test('user is set after /api/me resolves with 200', async () => {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve({ username: 'alice' }),
  });

  const { result } = renderHook(() => useAuth(), { wrapper });

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.user).toEqual({ username: 'alice' });
});

test('user stays null when /api/me returns 401', async () => {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: false,
    status: 401,
    json: () => Promise.resolve({ detail: 'Not logged in' }),
  });

  const { result } = renderHook(() => useAuth(), { wrapper });

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.user).toBe(null);
});

// ---------------------------------------------------------------------------
// login()
// ---------------------------------------------------------------------------

test('login() throws on bad credentials', async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ // /api/me on mount → not logged in
      ok: false,
      json: () => Promise.resolve({ detail: 'Not logged in' }),
    })
    .mockResolvedValueOnce({ // /api/login → bad creds
      ok: false,
      json: () => Promise.resolve({ detail: 'Invalid username or password' }),
    });

  const { result } = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));

  await expect(
    act(() => result.current.login('bad', 'creds'))
  ).rejects.toThrow('Invalid username or password');
});

test('login() sets user on success', async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ // /api/me on mount → not logged in
      ok: false,
      json: () => Promise.resolve({ detail: 'Not logged in' }),
    })
    .mockResolvedValueOnce({ // /api/login → success
      ok: true,
      json: () => Promise.resolve({ username: 'bob', status: 'ok' }),
    });

  const { result } = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));

  await act(() => result.current.login('bob', 'pass'));
  // window.location.reload() is mocked via the custom env — just verify user was set
  expect(result.current.user).toEqual({ username: 'bob' });
});

// ---------------------------------------------------------------------------
// logout()
// ---------------------------------------------------------------------------

test('logout() clears user state', async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ username: 'alice' }) }) // /api/me
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) }); // /api/logout

  const { result } = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(result.current.user).toEqual({ username: 'alice' }));

  await act(() => result.current.logout());
  expect(result.current.user).toBe(null);
});

// ---------------------------------------------------------------------------
// Auth Modal state
// ---------------------------------------------------------------------------

test('openAuthModal sets isAuthModalOpen to true', async () => {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: false,
    json: () => Promise.resolve({}),
  });

  const { result } = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));

  expect(result.current.isAuthModalOpen).toBe(false);
  act(() => result.current.openAuthModal());
  expect(result.current.isAuthModalOpen).toBe(true);
});

test('closeAuthModal sets isAuthModalOpen to false', async () => {
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: false,
    json: () => Promise.resolve({}),
  });

  const { result } = renderHook(() => useAuth(), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));

  act(() => result.current.openAuthModal());
  act(() => result.current.closeAuthModal());
  expect(result.current.isAuthModalOpen).toBe(false);
});
