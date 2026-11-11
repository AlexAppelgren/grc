import { notFound } from 'next/navigation';
import { connection } from 'next/server';
import type { ReactNode } from 'react';

// The pill gallery and the Green spike are tools for the E2E journeys and for whoever
// builds the screens, never pages of the product (review 2026-11-11 L-9). They answer
// "not found" unless the server was started with E2E_DEV_PAGES=1, which only
// playwright.config.ts sets. `connection()` reads the variable per request, so a build
// made without it (CI builds before the journeys start) still serves them under E2E.
export default async function DevLayout({ children }: { children: ReactNode }) {
  await connection();
  if (process.env.E2E_DEV_PAGES !== '1') notFound();
  return children;
}
