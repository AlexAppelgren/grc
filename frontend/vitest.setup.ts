import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// findBy* and waitFor give up after testing-library's default of 1000 ms. Screens that wait
// on the api client (a cold-load refresh, then the real request, then renders) took 1261 ms
// under a loaded machine on 2026-09-19 and failed an otherwise green suite. 5000 ms suits
// every test of that kind; a real failure still fails, only later.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});
