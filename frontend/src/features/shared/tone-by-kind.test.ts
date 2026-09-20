import { describe, expect, it } from 'vitest';

import { pillToneNames } from '@/components/ui/pill-tones';

import { apiKeyStateTone, checkStatusTone, slotTone } from './tone-by-kind';

// The chunk 5 entries, pinned against design/system/pills-and-labels.md and
// the cards. A tone comes from the row's own kind or from the slot it sits
// in; nothing here may become a choice a person makes.

describe('tone by kind: the watch and console entries', () => {
  it('reads the outcome of a source check off the check, not off its text', () => {
    expect(checkStatusTone.ok).toBe('positive');
    expect(checkStatusTone.failed).toBe('negative');
    expect(Object.keys(checkStatusTone)).toEqual(['ok', 'failed']);
  });

  it('reads the state of an agent key off its own facts', () => {
    expect(apiKeyStateTone.active).toBe('positive');
    expect(apiKeyStateTone.never_used).toBe('information');
    expect(apiKeyStateTone.revoked).toBe('warning');
    expect(apiKeyStateTone.expired).toBe('warning');
  });

  it('gives the watch and console slots the tones the cards draw', () => {
    expect(slotTone.suggested).toBe('information');
    expect(slotTone.confirmed).toBe('positive');
    expect(slotTone.factsToConfirm).toBe('warning');
    expect(slotTone.duplicate).toBe('information');
    expect(slotTone.agentVersion).toBe('brand');
    expect(slotTone.apiScope).toBe('information');
    expect(slotTone.sourceKind).toBe('information');
    expect(slotTone.paused).toBe('information');
  });

  it('takes every tone from the six, so no seventh can be introduced here', () => {
    const tones = [...Object.values(checkStatusTone), ...Object.values(apiKeyStateTone), ...Object.values(slotTone)];
    for (const tone of tones) expect(pillToneNames).toContain(tone);
  });
});
