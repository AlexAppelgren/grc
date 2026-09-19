import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vitest/config';

// Unit tests beside the code. Coverage thresholds per directory are a
// ratchet (playbook 8.2): the floor sits just below what was measured, and
// only moves up. Measured 2026-09-19 (Phase 0): see the numbers beside each
// entry; re-measure with `npm run test:coverage` before raising.
export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@tests': fileURLToPath(new URL('./tests', import.meta.url)),
    },
  },
  oxc: { jsx: { runtime: 'automatic' } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      include: ['src/features/**', 'src/components/vocabularies/**', 'src/shared/utils/**', 'src/shared/webauthn.ts', 'src/components/ui/**', 'src/shared/i18n/**', 'src/shared/navigation/**'],
      exclude: ['**/*.test.{ts,tsx}', '**/*.d.ts', 'src/features/**/types.ts'],
      thresholds: {
        // Measured 2026-09-19 (chunk 1, 12 test files): lines 100.0, branches 98.7, functions 100.0, statements 100.0
        'src/features/**': { lines: 98, branches: 98, functions: 98, statements: 98 },
        // Measured 2026-09-19 (chunk 2, 5 test files): lines 100.0, branches 98.3, functions 100.0, statements 99.4.
        // The two branches left are unreachable guards (a bigram set is never empty; a near_duplicate body is always an object).
        'src/features/vocabularies/**': { lines: 99, branches: 98, functions: 99, statements: 99 },
        // Measured 2026-09-19 (chunk 2, 5 test files): lines 100.0, branches 100.0, functions 100.0, statements 100.0
        'src/features/footprint/**': { lines: 99, branches: 99, functions: 99, statements: 99 },
        // Measured 2026-09-19 (chunk 2, the picker, 1 test file): lines 100.0, branches 98.9, functions 100.0, statements 99.0
        'src/components/vocabularies/**': { lines: 99, branches: 98, functions: 99, statements: 98 },
        // Measured 2026-09-19 (chunk 1, 6 test files): lines 99.2, branches 96.5, functions 100.0, statements 98.6
        'src/shared/utils/**': { lines: 97, branches: 94, functions: 98, statements: 97 },
        // Measured 2026-09-19 (chunk 1, 16 tests): lines 100.0, branches 96.0, functions 100.0, statements 100.0
        'src/shared/webauthn.ts': { lines: 97, branches: 92, functions: 98, statements: 97 },
        // Measured 2026-09-19 (chunk 1, 3 test files): lines 100.0, branches 98.5, functions 100.0, statements 100.0
        'src/components/ui/**': { lines: 98, branches: 98, functions: 98, statements: 98 },
        // Measured 2026-09-19: lines 100.0, branches 85.7, functions 100.0, statements 97.4
        'src/shared/i18n/**': { lines: 98, branches: 83, functions: 98, statements: 95 },
        // Measured 2026-09-19: lines 100.0, branches 93.5, functions 100.0, statements 100.0
        'src/shared/navigation/**': { lines: 98, branches: 91, functions: 98, statements: 98 },
      },
    },
  },
});
