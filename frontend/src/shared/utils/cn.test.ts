import { describe, expect, it } from 'vitest';

import { cn } from './cn';

describe('cn', () => {
  it('merges conditional classes and resolves Tailwind conflicts', () => {
    expect(cn('px-2', { hidden: false, block: true }, ['py-1'])).toBe('px-2 block py-1');
    expect(cn('px-2 px-4')).toBe('px-4');
  });

  it('knows the named type scale, so a size and a colour never cancel each other', () => {
    expect(cn('text-meta', 'text-muted')).toBe('text-meta text-muted');
    expect(cn('text-body', 'text-meta')).toBe('text-meta');
  });
});
