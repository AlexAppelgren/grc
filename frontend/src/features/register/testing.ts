import type { RegisterPanels } from './types';

// Test fixtures only. The register read as the server answers it: an entry with the first
// page of every panel beside it, empty unless a test names a part.

const EMPTY = { items: [], total: 0 };

export const NO_PANELS: RegisterPanels = {
  spannedEntities: [],
  gaps: EMPTY,
  assessments: EMPTY,
  internalLinks: EMPTY,
  units: null,
  participants: EMPTY,
  problemReports: null,
  changes: null,
  comments: null,
};

export function withPanels<T extends object>(entry: T, parts: Partial<RegisterPanels> = {}): T & { panels: RegisterPanels } {
  return { ...entry, panels: { ...NO_PANELS, ...parts } };
}
