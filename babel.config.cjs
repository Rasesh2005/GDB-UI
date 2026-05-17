/**
 * Babel config for Jest (frontend tests only).
 * This file enables Jest to understand JSX and modern JS/TS.
 *
 * Install required packages:
 *   cd "DOCKER VERSION 6"
 *   npm install --save-dev \
 *     @babel/preset-env \
 *     @babel/preset-react \
 *     @babel/preset-typescript \
 *     babel-jest
 */
module.exports = {
  presets: [
    ['@babel/preset-env', { targets: { node: 'current' } }],
    ['@babel/preset-react', { runtime: 'automatic' }],
    '@babel/preset-typescript',
  ],
};
