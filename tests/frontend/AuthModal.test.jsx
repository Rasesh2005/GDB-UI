/**
 * AuthModal.test.jsx — Section 6.1
 *
 * Component render + interaction tests for the AuthModal.
 *
 * WHY: AuthModal is the user-facing entry point for login and register.
 *      If a tab switch breaks, users can never register.
 *      If the error message is not shown, users don't know why login failed.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AuthModal from '../../frontend/src/components/AuthModal';
import { AuthProvider } from '../../frontend/src/contexts/AuthContext';

/**
 * Helper: render the AuthModal inside an AuthProvider with isOpen=true.
 */
const renderModal = (props = {}) =>
  render(
    <AuthProvider>
      <AuthModal isOpen={true} onClose={jest.fn()} {...props} />
    </AuthProvider>
  );

// ---------------------------------------------------------------------------
// Render tests
// ---------------------------------------------------------------------------

test('does not render when isOpen is false', () => {
  render(
    <AuthProvider>
      <AuthModal isOpen={false} onClose={() => {}} />
    </AuthProvider>
  );
  // WHY: An invisible modal must not pollute the DOM
  expect(screen.queryByText('Login')).not.toBeInTheDocument();
});

test('renders Login tab by default', () => {
  const { container } = renderModal();
  // The submit button should say "Login" (not "Create Account") on first render
  const submitBtn = container.querySelector('.submit-btn');
  expect(submitBtn).toHaveTextContent(/^login$/i);
});

test('username input is present', () => {
  renderModal();
  expect(screen.getByPlaceholderText(/enter your username/i)).toBeInTheDocument();
});

test('password input is present', () => {
  renderModal();
  expect(screen.getByPlaceholderText(/enter your password/i)).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

test('clicking Register tab shows Create Account button', () => {
  /**
   * WHY: Tab switching is pure state logic. If it breaks, users can never
   *      switch to Register and create an account.
   */
  const { container } = renderModal();
  fireEvent.click(screen.getByRole('button', { name: /register/i }));
  const submitBtn = container.querySelector('.submit-btn');
  expect(submitBtn).toHaveTextContent(/create account/i);
});

test('switching back from Register to Login shows Login button', () => {
  const { container } = renderModal();
  fireEvent.click(screen.getByRole('button', { name: /register/i }));
  
  // This targets the button inside the auth-tabs div
  const loginTab = container.querySelector('.auth-tabs button');
  fireEvent.click(loginTab);

  // The submit button text goes back to "Login"
  const submitBtn = container.querySelector('.submit-btn');
  expect(submitBtn).toHaveTextContent(/^login$/i);
});

// ---------------------------------------------------------------------------
// Error display
// ---------------------------------------------------------------------------

test('shows error message on failed login', async () => {
  /**
   * WHY: Without visible error feedback, users assume the app is broken
   *      rather than understanding they entered the wrong password.
   */
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) })   // /api/me → 401
    .mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Invalid username or password' }),
    }); // /api/login → 400

  const { container } = renderModal();

  fireEvent.change(screen.getByPlaceholderText(/enter your username/i), {
    target: { value: 'wronguser' },
  });
  fireEvent.change(screen.getByPlaceholderText(/enter your password/i), {
    target: { value: 'wrongpass' },
  });
  
  const submitBtn = container.querySelector('.submit-btn');
  fireEvent.click(submitBtn);

  await waitFor(() =>
    expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument()
  );
});

test('shows error message on failed registration', async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) })  // /api/me
    .mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Username already exists' }),
    }); // /api/register

  const { container } = renderModal();
  fireEvent.click(screen.getByRole('button', { name: /register/i }));

  fireEvent.change(screen.getByPlaceholderText(/enter your username/i), {
    target: { value: 'dup' },
  });
  fireEvent.change(screen.getByPlaceholderText(/enter your password/i), {
    target: { value: 'pass' },
  });
  
  const submitBtn = container.querySelector('.submit-btn');
  fireEvent.click(submitBtn);

  await waitFor(() =>
    expect(screen.getByText(/username already exists/i)).toBeInTheDocument()
  );
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

test('submit button shows Processing... while request is in flight', async () => {
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: false, json: () => Promise.resolve({}) }) // /api/me
    .mockImplementationOnce(
      () => new Promise(resolve => { /* resolveFetch = resolve; */ }) // Never resolves immediately
    );

  const { container } = renderModal();
  fireEvent.change(screen.getByPlaceholderText(/enter your username/i), { target: { value: 'u' } });
  fireEvent.change(screen.getByPlaceholderText(/enter your password/i), { target: { value: 'p' } });
  
  const submitBtn = container.querySelector('.submit-btn');
  fireEvent.click(submitBtn);

  await waitFor(() =>
    expect(screen.getByText(/processing/i)).toBeInTheDocument()
  );
});
