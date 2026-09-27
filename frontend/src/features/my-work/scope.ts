import type { WorkScope } from './types';

// Which view My work opens on (HOM-05, HOM-S9). A department head opens on
// their department; the choice they make is remembered on this device. The
// department view is a filter and never a grant, so any member may open one
// by its address (`/work?unit=<id>`); only heads get the switch for it.

const STORAGE_KEY = 'cw.myWork.scope';
const MINE = 'mine';

/** The remembered choice: `mine` or a department's id. Storage can be missing or refused. */
export function storedScope(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeScope(scope: WorkScope): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, scope.scope === 'unit' ? scope.unit : MINE);
  } catch {
    // Remembering is a convenience; the view still switches.
  }
}

/**
 * A department named in the address wins; then the remembered choice, while
 * the reader still heads that department; then a head's first department;
 * otherwise the reader's own work.
 */
export function initialScope(fromAddress: string | null, stored: string | null, headOf: readonly { id: string }[]): WorkScope {
  if (fromAddress !== null && fromAddress !== '') return { scope: 'unit', unit: fromAddress };
  if (stored === MINE) return { scope: 'mine' };
  const remembered = headOf.find((unit) => unit.id === stored);
  const first = remembered ?? headOf[0];
  return first === undefined ? { scope: 'mine' } : { scope: 'unit', unit: first.id };
}
