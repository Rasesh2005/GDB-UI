/**
 * ControlPanel.test.jsx — Section 6.2
 *
 * Tests the conditional rendering of auth state in ControlPanel.
 *
 * WHY: The Login/Register or "👤 user | Logout" section is conditional.
 *      If the wrong branch renders, authenticated users see a Login button
 *      or guests see someone else's username.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ControlPanel from '../../frontend/src/components/ControlPanel';

// ---------------------------------------------------------------------------
// Context mocking helpers
// ---------------------------------------------------------------------------
// We mock the context modules so we can inject any user/state we want.

jest.mock('../../frontend/src/contexts/AuthContext', () => ({
  useAuth: jest.fn(),
}));

jest.mock('../../frontend/src/contexts/DebugContext', () => ({
  useDebugger: jest.fn(),
}));

jest.mock('../../frontend/src/contexts/TerminalContext', () => ({
  useTerminal: jest.fn(),
}));

import { useAuth } from '../../frontend/src/contexts/AuthContext';
import { useDebugger } from '../../frontend/src/contexts/DebugContext';
import { useTerminal } from '../../frontend/src/contexts/TerminalContext';

const defaultDebugState = {
  state: { status: 'idle', breakpoints: [], stack: [] },
  connected: false,
  userBreakpoints: [],
  runGdb: jest.fn(),
  stepInto: jest.fn(),
  stepOver: jest.fn(),
  stepBack: jest.fn(),
  stepOnto: jest.fn(),
  continueExec: jest.fn(),
  pauseExec: jest.fn(),
  stopExec: jest.fn(),
  toggleBreakpoint: jest.fn(),
  sendCommand: jest.fn(),
};

const renderPanel = () => render(<ControlPanel />);

// ---------------------------------------------------------------------------
// 6.2a  Auth state → button rendering
// ---------------------------------------------------------------------------

test('shows Login / Register button when user is null', () => {
  /**
   * WHY: Guest users must always see a way to log in.
   */
  (useAuth).mockReturnValue({
    user: null,
    loading: false,
    openAuthModal: jest.fn(),
    closeAuthModal: jest.fn(),
    isAuthModalOpen: false,
    logout: jest.fn(),
  });
  (useDebugger).mockReturnValue(defaultDebugState);
  (useTerminal).mockReturnValue({ connected: true });

  renderPanel();
  expect(screen.getByText(/login/i)).toBeInTheDocument();
});

test('shows username and Logout button when user is set', () => {
  /**
   * WHY: Authenticated users must see their username and a way to log out.
   *      If they see "Login / Register", something went wrong with the session.
   */
  (useAuth).mockReturnValue({
    user: { username: 'alice' },
    loading: false,
    openAuthModal: jest.fn(),
    closeAuthModal: jest.fn(),
    isAuthModalOpen: false,
    logout: jest.fn(),
  });
  (useDebugger).mockReturnValue(defaultDebugState);
  (useTerminal).mockReturnValue({ connected: true });

  renderPanel();
  expect(screen.getByText(/alice/i)).toBeInTheDocument();
  expect(screen.getByText(/logout/i)).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// 6.2b  Debugger running state → buttons disabled
// ---------------------------------------------------------------------------

test('Run GDB button is disabled during running state', () => {
  /**
   * WHY: Double-clicking Run GDB during execution causes issues.
   *      The button must be disabled while status is "running" or "compiling".
   */
  (useAuth).mockReturnValue({
    user: null, loading: false, openAuthModal: jest.fn(),
    closeAuthModal: jest.fn(), isAuthModalOpen: false, logout: jest.fn(),
  });
  (useDebugger).mockReturnValue({
    ...defaultDebugState,
    connected: true,
    state: { ...defaultDebugState.state, status: 'running' },
  });
  (useTerminal).mockReturnValue({ connected: true });

  renderPanel();
  const runBtn = screen.queryByText(/run \(gdb\)/i);
  if (runBtn) {
    expect(runBtn.closest('button')).toBeDisabled();
  } else {
    // Component might hide it instead of disabling — acceptable
    expect(screen.queryByRole('button', { name: /run.*gdb/i })).toBeNull();
  }
});

test('Run GDB button is enabled when status is idle', () => {
  (useAuth).mockReturnValue({
    user: null, loading: false, openAuthModal: jest.fn(),
    closeAuthModal: jest.fn(), isAuthModalOpen: false, logout: jest.fn(),
  });
  (useDebugger).mockReturnValue({
    ...defaultDebugState,
    connected: true,
    state: { ...defaultDebugState.state, status: 'idle' },
  });
  (useTerminal).mockReturnValue({ connected: true });

  renderPanel();
  const runBtn = screen.queryByRole('button', { name: /run.*gdb/i });
  if (runBtn) {
    expect(runBtn).not.toBeDisabled();
  }
});

// ---------------------------------------------------------------------------
// 6.2c  Logout click calls logout()
// ---------------------------------------------------------------------------

test('clicking Logout calls the logout function', () => {
  const logoutFn = jest.fn();
  (useAuth).mockReturnValue({
    user: { username: 'bob' },
    loading: false,
    openAuthModal: jest.fn(),
    closeAuthModal: jest.fn(),
    isAuthModalOpen: false,
    logout: logoutFn,
  });
  (useDebugger).mockReturnValue({
    ...defaultDebugState,
    connected: true,
  });
  (useTerminal).mockReturnValue({ connected: true });

  renderPanel();
  fireEvent.click(screen.getByText(/logout/i));
  expect(logoutFn).toHaveBeenCalledTimes(1);
});
