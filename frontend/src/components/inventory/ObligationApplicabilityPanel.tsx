import type { Applicability, RegisterEntry } from '@/features/register/types';

// "Does it apply?": the answer per legal entity where the obligation spans
// several, else for the obligation as a whole, each with its reason and who set
// it when (REG-01, D-42). The answers are drawn per company in "Our position"
// (ObligationPositionPanel), which sets one through the dialog "What applies"
// uses (components/applies/DecideDialog.tsx, D-141); this file holds which
// answers there are. One person holding applicability.approve answers, and the
// answer is stored at once with no second person and no passkey (D-75). The
// compliance status is never read or written here: "applies" and "we comply"
// are separate.

export const APPROVE_PERMISSION = 'applicability.approve';

/** One answer the page shows: the whole obligation (`orgUnitId` null) or one legal entity. */
export interface Answer {
  orgUnitId: string | null;
  name: string | null;
  applicability: Applicability;
  reason: string | null;
  decidedAt: string | null;
  decidedBy: string | null;
  version: number;
}

/**
 * Every entity the obligation spans, answered or not, then any entity row the
 * bank holds outside today's span; per entity only where there are several.
 * The whole obligation's own answer stays on show once someone gave it.
 */
export function answersOf(entry: RegisterEntry, spanned: readonly { orgUnitId: string; orgUnitName: string }[]): Answer[] {
  const rows = new Map(entry.entities.map((row) => [row.orgUnitId, row]));
  const outside = entry.entities.filter((row) => !spanned.some((entity) => entity.orgUnitId === row.orgUnitId));
  const named = [...spanned, ...outside.map((row) => ({ orgUnitId: row.orgUnitId, orgUnitName: row.orgUnitName }))];
  const entities: Answer[] = named.map(({ orgUnitId, orgUnitName }) => {
    const row = rows.get(orgUnitId);
    return {
      orgUnitId,
      name: orgUnitName,
      applicability: row?.applicability ?? 'under_assessment',
      reason: row?.applicabilityReason ?? null,
      decidedAt: row?.applicabilityDecidedAt ?? null,
      decidedBy: row?.applicabilityDecidedBy?.name ?? null,
      version: row?.version ?? 0,
    };
  });
  const whole: Answer = {
    orgUnitId: null,
    name: null,
    applicability: entry.applicability,
    reason: entry.applicabilityReason,
    decidedAt: entry.applicabilityDecidedAt,
    decidedBy: entry.applicabilityDecidedBy?.name ?? null,
    version: entry.version,
  };
  if (entities.length < 2) return [whole];
  return entry.applicability === 'under_assessment' ? entities : [whole, ...entities];
}
