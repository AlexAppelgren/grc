import { describe, expect, it } from 'vitest';

import { aiReviewTone, aiFeedbackTone } from '@/features/shared/tone-by-kind';
import { t } from '@/shared/i18n';

import { AI_PURPOSES, AI_REVIEW_STATES, keepsAiLabel, presentAiGeneration, purposeLabel, reviewLabel } from './ai-log-presentation';

// The AI log's pills (AUD-02): purpose in its slot tone, the review state and
// a reader's verdict toned by their kind, never by a person; the AI label
// stays on every row a person has not confirmed as it stands.

const translate = (key: Parameters<typeof t>[0], vars?: Parameters<typeof t>[1]) => t(key, vars);

describe('AI log presentation', () => {
  it('offers the purposes a bank can see, never the platform-only agent review', () => {
    expect(AI_PURPOSES).toEqual(['so_what', 'change_summary', 'scope_suggestion', 'link_suggestion', 'translation', 'answer']);
    expect(AI_PURPOSES).not.toContain('agent_review');
    expect(AI_REVIEW_STATES).toEqual(['draft', 'confirmed', 'edited', 'rejected']);
  });

  it('names each purpose and review state from the catalog, and a kind added later by its key', () => {
    expect(purposeLabel('so_what', translate)).toBe('So what?');
    expect(purposeLabel('answer', translate)).toBe('Ask answer');
    expect(purposeLabel('new_kind', translate)).toBe('new kind');
    expect(reviewLabel('draft', translate)).toBe('Not yet reviewed');
    expect(reviewLabel('edited', translate)).toBe('Rewritten');
    expect(reviewLabel('odd_state', translate)).toBe('odd state');
  });

  it('pills purpose, review state and verdict in that order, toned by kind', () => {
    expect(presentAiGeneration({ purpose: 'answer', status: 'draft', feedback: 'wrong' }, translate)).toEqual([
      { key: 'purpose:answer', label: 'Ask answer', tone: 'notice', order: 0 },
      { key: 'review:draft', label: 'Not yet reviewed', tone: 'information', order: 1 },
      { key: 'feedback:wrong', label: 'Marked wrong', tone: 'warning', order: 2 },
    ]);
    expect(presentAiGeneration({ purpose: 'so_what', status: 'confirmed', feedback: '' }, translate)).toEqual([
      { key: 'purpose:so_what', label: 'So what?', tone: 'notice', order: 0 },
      { key: 'review:confirmed', label: 'Confirmed', tone: 'positive', order: 1 },
    ]);
    expect(presentAiGeneration({ purpose: 'answer', status: 'draft', feedback: 'helpful' }, translate)[2]).toEqual({ key: 'feedback:helpful', label: 'Marked helpful', tone: 'positive', order: 2 });
  });

  it('tones every review state and verdict by its kind', () => {
    expect(aiReviewTone).toEqual({ draft: 'information', confirmed: 'positive', edited: 'positive', rejected: 'information' });
    expect(aiFeedbackTone).toEqual({ helpful: 'positive', wrong: 'warning' });
  });

  it('gives an unknown review state or verdict a neutral tone rather than none', () => {
    const pills = presentAiGeneration({ purpose: 'answer', status: 'odd_state', feedback: 'meh' }, translate);
    expect(pills.map((pill) => pill.tone)).toEqual(['notice', 'information', 'information']);
  });

  it('keeps the AI label until a person confirmed the words as they stand', () => {
    expect(keepsAiLabel('draft')).toBe(true);
    expect(keepsAiLabel('edited')).toBe(true);
    expect(keepsAiLabel('rejected')).toBe(true);
    expect(keepsAiLabel('confirmed')).toBe(false);
  });
});
