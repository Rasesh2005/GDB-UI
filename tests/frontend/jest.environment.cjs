/**
 * jest.environment.cjs — Custom Jest/JSDOM 30 environment.
 *
 * JSDOM 30+ sets window.location as non-configurable on the Window INSTANCE
 * after creation. The fix: override the location getter on the Window CLASS
 * prototype BEFORE the test environment creates its window instance.
 *
 * Strategy: subclass TestEnvironment, then in setup() use the internal
 * this.global (which is the vm sandbox) with Reflect to rewrite the property.
 */

'use strict';

const { TestEnvironment } = require('jest-environment-jsdom');

class CustomJSDOMEnvironment extends TestEnvironment {
  constructor(config, context) {
    super(config, context);
  }

  async setup() {
    await super.setup();

    // Suppress JSDOM's VirtualConsole 'jsdomError' events for navigation.
    // These are emitted on a separate channel from console.error and show up
    // as "Error: Not implemented: navigation (except hash changes)" in test output
    // even when the real console.error is overridden in jest.setup.ts.
    if (this.dom?.virtualConsole) {
      const vc = this.dom.virtualConsole;
      const origJsdomError = vc.emit.bind(vc);
      vc.emit = (type, ...args) => {
        if (type === 'jsdomError') {
          const err = args[0];
          if (err && err.type === 'not implemented') {
            return false; // swallow it
          }
        }
        return origJsdomError(type, ...args);
      };
    }

    // After setup(), this.global is the JSDOM window proxy.
    // Use Reflect.defineProperty with force-configurable = true.
    // This works because jest-environment-jsdom wraps the window in a Proxy
    // that does NOT enforce the original descriptor's configurable flag.
    const win = this.global;

    try {
      // Try Reflect.defineProperty on the proxied window — JSDOM's Proxy
      // intercepts this differently from Object.defineProperty.
      const currentLocation = win.location;

      Reflect.defineProperty(win, 'location', {
        configurable: true,
        enumerable: true,
        writable: false,
        value: {
          href: currentLocation.href || 'http://localhost/',
          protocol: currentLocation.protocol || 'http:',
          host: currentLocation.host || 'localhost',
          hostname: currentLocation.hostname || 'localhost',
          port: currentLocation.port || '',
          pathname: currentLocation.pathname || '/',
          search: currentLocation.search || '',
          hash: currentLocation.hash || '',
          origin: currentLocation.origin || 'http://localhost',
          reload: jest.fn(),
          assign: jest.fn(),
          replace: jest.fn(),
          toString() { return this.href; },
        },
      });
    } catch {
      // Fallback: if Reflect.defineProperty also fails, patch reload directly
      // on the existing location object using the internal [[Set]] operation
      // via the Proxy's set trap (which IS allowed even for non-configurable).
      try {
        win.location.reload = () => {};
        win.location.assign = () => {};
        win.location.replace = () => {};
      } catch {
        // Completely frozen — do nothing, console.error suppression in
        // jest.setup.ts will silence the "Not implemented" warnings.
      }
    }
  }
}

module.exports = CustomJSDOMEnvironment;
