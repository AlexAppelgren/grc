import { describe, expect, it } from 'vitest';

import { bodyRefusal } from './api-body';

const LIMIT = 1000;

describe('bodyRefusal', () => {
  it('lets a call without a body through, and a body up to the limit', () => {
    expect(bodyRefusal(null, null, LIMIT)).toBeNull();
    expect(bodyRefusal('0', null, LIMIT)).toBeNull();
    expect(bodyRefusal('1000', null, LIMIT)).toBeNull();
  });

  it('refuses a body above the limit, in the API problem format', () => {
    expect(bodyRefusal('1001', null, LIMIT)).toEqual({ title: 'Content Too Large', status: 413, detail: 'This is too large to send. Choose a smaller file.', code: 'payload_too_large' });
  });

  it('refuses a body that does not say how large it is, whatever else it says', () => {
    expect(bodyRefusal(null, 'chunked', LIMIT)?.status).toBe(411);
    expect(bodyRefusal('10', 'chunked', LIMIT)?.code).toBe('length_required');
  });
});
