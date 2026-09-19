import { describe, expect, it } from 'vitest';

import { movesNothing } from './FootprintScreen';
import { moveKey } from './VocabularyScreen';

// Pure helpers the chunk 2 screens lean on.

describe('moveKey (drag and arrow-key reorder)', () => {
  const keys = ['custody', 'advice', 'onboarding'];

  it('moves a key to a new position and keeps the rest in order', () => {
    expect(moveKey(keys, 'onboarding', 0)).toEqual(['onboarding', 'custody', 'advice']);
    expect(moveKey(keys, 'custody', 1)).toEqual(['advice', 'custody', 'onboarding']);
  });

  it('clamps at both ends, so an arrow key past the edge is a no-op', () => {
    expect(moveKey(keys, 'custody', -1)).toEqual(keys);
    expect(moveKey(keys, 'onboarding', 99)).toEqual(keys);
  });

  it('leaves the order alone for a key it does not hold, and never mutates its input', () => {
    expect(moveKey(keys, 'unknown', 0)).toEqual(keys);
    moveKey(keys, 'advice', 0);
    expect(keys).toEqual(['custody', 'advice', 'onboarding']);
  });
});

describe('movesNothing (the preview side reads "Nothing.")', () => {
  it('is true only when every count is known and zero', () => {
    expect(movesNothing(undefined)).toBe(true);
    expect(movesNothing({})).toBe(true);
    expect(movesNothing({ obligations: { count: 0, available: true } })).toBe(true);
    expect(movesNothing({ obligations: { count: 4, available: true } })).toBe(false);
  });

  it('never claims nothing moves while a count is still unknown', () => {
    expect(movesNothing({ obligations: { count: 0, available: true }, cases: { count: 0, available: false } })).toBe(false);
  });
});
