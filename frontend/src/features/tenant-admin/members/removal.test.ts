import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import { kindsStillOwned, movedWork, participationCount, removalBody, type OpenWork } from './removal';

// The removal's pure parts: the kinds that move, in the screen's order and
// with the server's counts; what simply ends; the body, one owner per kind;
// and a reassignment_required answer read from its code and errors.

const work: OpenWork = {
  member: { id: 'u-gustav', name: 'Gustav Sjöberg' },
  items: [
    { kind: 'action', count: 4 },
    { kind: 'participation', count: 5 },
    { kind: 'register_entry', count: 3 },
    { kind: 'team_membership', count: 2 },
    { kind: 'gap', count: 1 },
  ],
  teams: ['cards', 'legal'],
};

function problem(status: number, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  return new AxiosError('refused', String(status), config, undefined, { data, status, statusText: '', headers: {}, config });
}

describe('the removal', () => {
  it('lists the kinds that move in the screen order, and counts what ends', () => {
    expect(movedWork(work)).toEqual([
      { kind: 'register_entry', count: 3 },
      { kind: 'gap', count: 1 },
      { kind: 'action', count: 4 },
    ]);
    expect(participationCount(work)).toBe(5);
    expect(participationCount({ ...work, items: [] })).toBe(0);
  });

  it('sends one owner per kind, a team by key or a person by id', () => {
    expect(removalBody({ register_entry: { userId: 'u-sara' }, gap: { teamKey: 'cards' } })).toEqual({
      owners: [
        { kind: 'register_entry', userId: 'u-sara' },
        { kind: 'gap', teamKey: 'cards' },
      ],
    });
    expect(removalBody({})).toEqual({ owners: [] });
  });

  it('reads the kinds still owned from reassignment_required, and nothing from another refusal', () => {
    const refused = problem(422, {
      code: 'reassignment_required',
      detail: 'Anything at all.',
      errors: [
        { field: 'gap', count: 2, message: 'x' },
        { field: 'participation', count: 1, message: 'x' },
      ],
    });
    expect(kindsStillOwned(refused)).toEqual([{ kind: 'gap', count: 2 }]);
    expect(kindsStillOwned(problem(422, { code: 'unknown_member', detail: '', errors: [{ field: 'gap', count: 2 }] }))).toEqual([]);
    expect(kindsStillOwned(null)).toEqual([]);
  });
});
