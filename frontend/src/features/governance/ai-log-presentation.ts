import type { PresentedPill } from '@/features/shared/presentation-types';
import { aiFeedbackTone, aiReviewTone, slotTone, type AiFeedbackKind, type AiReviewKind } from '@/features/shared/tone-by-kind';
import { humaniseKey } from '@/features/tenant-admin/members-presentation';
import type { MessageKey, Translate } from '@/shared/i18n';

import type { AiGeneration } from './types';

// Pills and labels for the AI log (AUD-02). The API sends kinds; the catalog
// names them, and a kind the backend adds later still reads, by its key with
// the separators opened up, as the audit log does. Tone comes from the slot
// (purpose) or the kind (review state, verdict), never from a person.

const ORDER = { purpose: 0, review: 1, feedback: 2 };

/**
 * The purposes the filter offers: every kind a bank's log can hold. A
 * confirming agent's decision (`agent_review`) is the platform's alone, so a
 * bank's log never lists one and the filter does not offer it.
 */
export const AI_PURPOSES = ['so_what', 'change_summary', 'scope_suggestion', 'link_suggestion', 'translation', 'answer'] as const;

export const AI_REVIEW_STATES = ['draft', 'confirmed', 'edited', 'rejected'] as const satisfies readonly AiReviewKind[];

const PURPOSE_LABELS: Record<(typeof AI_PURPOSES)[number], MessageKey> = {
  so_what: 'admin.aiLog.purpose.so_what',
  change_summary: 'admin.aiLog.purpose.change_summary',
  scope_suggestion: 'admin.aiLog.purpose.scope_suggestion',
  link_suggestion: 'admin.aiLog.purpose.link_suggestion',
  translation: 'admin.aiLog.purpose.translation',
  answer: 'admin.aiLog.purpose.answer',
};

const REVIEW_LABELS: Record<AiReviewKind, MessageKey> = {
  draft: 'admin.aiLog.review.draft',
  confirmed: 'admin.aiLog.review.confirmed',
  edited: 'admin.aiLog.review.edited',
  rejected: 'admin.aiLog.review.rejected',
};

const FEEDBACK_LABELS: Record<AiFeedbackKind, MessageKey> = {
  helpful: 'admin.aiLog.feedback.helpful',
  wrong: 'admin.aiLog.feedback.wrong',
};

function known<K extends string>(map: Record<K, unknown>, key: string): key is K {
  return Object.hasOwn(map, key);
}

export function purposeLabel(purpose: string, t: Translate): string {
  return known(PURPOSE_LABELS, purpose) ? t(PURPOSE_LABELS[purpose]) : humaniseKey(purpose);
}

export function reviewLabel(status: string, t: Translate): string {
  return known(REVIEW_LABELS, status) ? t(REVIEW_LABELS[status]) : humaniseKey(status);
}

export function presentAiGeneration(row: Pick<AiGeneration, 'purpose' | 'status' | 'feedback'>, t: Translate): PresentedPill[] {
  const pills: PresentedPill[] = [
    { key: `purpose:${row.purpose}`, label: purposeLabel(row.purpose, t), tone: slotTone.aiPurpose, order: ORDER.purpose },
    { key: `review:${row.status}`, label: reviewLabel(row.status, t), tone: known(aiReviewTone, row.status) ? aiReviewTone[row.status] : 'information', order: ORDER.review },
  ];
  if (row.feedback !== '') {
    pills.push({
      key: `feedback:${row.feedback}`,
      label: known(FEEDBACK_LABELS, row.feedback) ? t(FEEDBACK_LABELS[row.feedback]) : humaniseKey(row.feedback),
      tone: known(aiFeedbackTone, row.feedback) ? aiFeedbackTone[row.feedback] : 'information',
      order: ORDER.feedback,
    });
  }
  return pills;
}

/** AI output stays labelled until a person confirmed the words as they stand; a rewrite or a rejection leaves the model's words on screen. */
export function keepsAiLabel(status: string): boolean {
  return status !== 'confirmed';
}
