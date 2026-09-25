import { beforeEach, describe, expect, it } from 'vitest';

import { installAdapter, resetApiForTests } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import * as problemReports from './api';

// The two wrappers: the record's reports as query parameters, and the close as
// a PATCH carrying the state and the note.

describe('problem reports api', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it("reads one record's reports and closes one", async () => {
    const closed = { id: 'r1', status: 'answered' };
    const sent = installAdapter((s) => (s.method === 'get' ? { status: 200, data: { items: [], total: 0 } } : { status: 200, data: closed }));
    expect(await problemReports.listProblemReports({ subjectType: 'obligation', subjectId: 'ob-1', limit: 20, offset: 0 })).toEqual({ items: [], total: 0 });
    expect(await problemReports.closeProblemReport('r1', { status: 'answered', resolutionNote: 'Version 2 says ten years.' })).toEqual(closed);
    expect(sent.map((s) => [s.method, s.path, s.params, s.body, s.authorization])).toEqual([
      ['get', '/api/v1/problem-reports', { subjectType: 'obligation', subjectId: 'ob-1', limit: 20, offset: 0 }, null, 'Bearer tok'],
      ['patch', '/api/v1/problem-reports/r1', null, { status: 'answered', resolutionNote: 'Version 2 says ten years.' }, 'Bearer tok'],
    ]);
  });
});
