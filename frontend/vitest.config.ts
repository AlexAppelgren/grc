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
      include: ['src/features/**', 'src/shared/utils/**', 'src/components/ui/**', 'src/shared/i18n/**', 'src/shared/navigation/**'],
      exclude: ['**/*.test.{ts,tsx}', '**/*.d.ts'],
      thresholds: {
        // Measured 2026-09-19: lines 100.0, branches 100.0, functions 100.0, statements 100.0
        'src/features/**': { lines: 98, branches: 98, functions: 98, statements: 98 },
        // Measured 2026-09-19: lines 99.0, branches 96.3, functions 100.0, statements 99.1
        'src/shared/utils/**': { lines: 97, branches: 94, functions: 98, statements: 97 },
        // Measured 2026-09-19: lines 100.0, branches 100.0, functions 100.0, statements 100.0
        'src/components/ui/**': { lines: 98, branches: 98, functions: 98, statements: 98 },
        // Measured 2026-09-19: lines 100.0, branches 85.7, functions 100.0, statements 97.4
        'src/shared/i18n/**': { lines: 98, branches: 83, functions: 98, statements: 95 },
        // Measured 2026-09-19: lines 100.0, branches 93.5, functions 100.0, statements 100.0
        'src/shared/navigation/**': { lines: 98, branches: 91, functions: 98, statements: 98 },
      },
    },
  },
});
