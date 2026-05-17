/**
 * jest.config.cjs — Jest configuration for frontend tests.
 *
 * Uses Babel to transform JSX/TSX and ESM modules.
 * Place this file in the project root ("DOCKER VERSION 6/").
 *
 * Run:  npx jest --config jest.config.cjs
 */

module.exports = {
  // Custom JSDOM environment that patches window.location before tests run.
  // Required because JSDOM 30 freezes window.location at the native level.
  testEnvironment: './tests/frontend/jest.environment.cjs',

  // Transform JSX and modern JS with babel-jest
  transform: {
    '^.+\\.[jt]sx?$': 'babel-jest',
  },

  // Tell Jest that .jsx and .tsx are valid extensions
  moduleFileExtensions: ['js', 'jsx', 'ts', 'tsx', 'json'],

  // Run the global setup file before every test suite
  setupFilesAfterEnv: ['./tests/frontend/jest.setup.ts'],

  // Discover test files under tests/frontend/
  testMatch: [
    '<rootDir>/tests/frontend/**/*.test.[jt]sx',
    '<rootDir>/tests/frontend/**/*.test.[jt]s',
  ],

  // Map CSS / static imports to stubs so they don't break tests
  moduleNameMapper: {
    '\\.(css|less|scss|sass)$': '<rootDir>/__mocks__/styleMock.cjs',
    '\\.(gif|png|jpg|jpeg|svg|webp|woff|woff2|ttf|eot)$':
      '<rootDir>/__mocks__/fileMock.cjs',

    // -------------------------------------------------------------------------
    // CRITICAL: pin React to a single instance.
    // The project has TWO node_modules trees:
    //   - <root>/node_modules/   (where Jest + babel-jest live)
    //   - <root>/frontend/node_modules/  (where the source components import from)
    //
    // Without this mapping, Jest resolves "react" from the root copy while the
    // component code loaded from frontend/src/ uses the frontend copy.
    // Two React instances crash hooks with "Cannot read properties of null".
    // -------------------------------------------------------------------------
    '^react$': '<rootDir>/frontend/node_modules/react',
    '^react/(.*)$': '<rootDir>/frontend/node_modules/react/$1',
    '^react-dom$': '<rootDir>/frontend/node_modules/react-dom',
    '^react-dom/(.*)$': '<rootDir>/frontend/node_modules/react-dom/$1',
    '^@testing-library/react$': '<rootDir>/node_modules/@testing-library/react',
  },

  // Collect coverage from source files only
  collectCoverageFrom: [
    'frontend/src/**/*.{js,jsx,ts,tsx}',
    '!frontend/src/main.jsx',        // Entry point — no logic to test
    '!frontend/src/**/*.d.ts',
  ],

  // Transform node_modules that ship as ESM
  transformIgnorePatterns: [
    '/node_modules/(?!(@monaco-editor|lucide-react|xterm|react-resizable-panels))',
  ],
};
