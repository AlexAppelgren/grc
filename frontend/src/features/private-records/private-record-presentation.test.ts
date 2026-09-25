import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';
import { defaultFormatContext } from '@/shared/utils/format';

import { payloadRows, presentPrivateProposal, proposerLine, sourceHost, sourcesOf } from './private-record-presentation';
import type { PrivateProposalRow } from './types';

const t = createT('en');
const sv = createT('sv');

const RIKSDAGEN = 'https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-2010751-om-betaltjanster_sfs-2010-751/';
const FI = 'https://www.fi.se/sv/betalningar/';

const agentRow: PrivateProposalRow = {
  id: 'p-1',
  kind: 'new_obligation',
  status: 'open',
  title: 'Add obligation: give the payer the prescribed information before a single payment',
  origin: 'agent',
  isMine: false,
  payload: {
    key: 'obl-own-psd-pre-payment-info',
    instrument: 'sfs-2010-751',
    titles: { sv: 'Ge betalaren informationen före en enstaka betalning', en: 'Give the payer the information before a single payment' },
    summaries: { sv: 'Innan betalaren blir bunden ska informationen lämnas.' },
    originalLanguage: 'sv',
    isMachine: true,
    refLabel: '4 kap.',
    dutyType: 'disclosure',
    effectiveFrom: '2010-05-01',
    terms: ['regime:payments'],
  },
  fieldSources: { 'titles.sv': RIKSDAGEN, 'summaries.sv': RIKSDAGEN, dutyType: RIKSDAGEN, terms: FI },
  sourceUrl: RIKSDAGEN,
  createdAt: '2026-09-25T04:04:00Z',
};

describe('presentPrivateProposal', () => {
  it('reads kind, status and "Proposed by our agent" in the card\'s tones', () => {
    expect(presentPrivateProposal(agentRow, t).map((p) => [p.label, p.tone])).toEqual([
      ['New obligation', 'notice'],
      ['Waiting', 'warning'],
      ['Proposed by our agent', 'brand'],
    ]);
  });

  it('gives a person\'s proposal no agent pill, and a decided one its status tone', () => {
    const row = { ...agentRow, origin: 'user', kind: 'new_instrument' };
    expect(presentPrivateProposal({ ...row, status: 'approved' }, t).map((p) => [p.label, p.tone])).toEqual([
      ['New instrument', 'notice'],
      ['Approved', 'positive'],
    ]);
    expect(presentPrivateProposal({ ...row, status: 'rejected' }, t).map((p) => [p.label, p.tone])).toEqual([
      ['New instrument', 'notice'],
      ['Rejected', 'information'],
    ]);
  });

  it('reads in Swedish, and a kind it does not know reads as a proposal', () => {
    expect(presentPrivateProposal(agentRow, sv).map((p) => p.label)).toEqual(['Ny skyldighet', 'Väntar', 'Föreslagen av vår agent']);
    expect(presentPrivateProposal({ ...agentRow, kind: 'something_new' }, t)[0]?.label).toBe('Proposal');
  });
});

describe('proposerLine', () => {
  it('leaves the agent to its pill and names a person as you or a colleague', () => {
    expect(proposerLine(agentRow, t)).toBeNull();
    expect(proposerLine({ origin: 'user', isMine: true }, t)).toBe('Proposed by you');
    expect(proposerLine({ origin: 'user', isMine: false }, t)).toBe('Proposed by a colleague');
  });
});

describe('sources', () => {
  it('numbers each distinct source once, the record\'s own first', () => {
    expect(sourcesOf(agentRow)).toEqual([RIKSDAGEN, FI]);
    expect(sourcesOf({ sourceUrl: '', fieldSources: {} })).toEqual([]);
  });

  it('names a link by its host and never makes a link of anything but http or https', () => {
    expect(sourceHost(RIKSDAGEN)).toBe('riksdagen.se');
    expect(sourceHost('javascript:alert(1)')).toBeNull();
    expect(sourceHost('not a url')).toBeNull();
  });
});

describe('payloadRows', () => {
  it('lists each field the proposal sets beside the number of its source, texts per language', () => {
    expect(payloadRows(agentRow, t, defaultFormatContext).map((row) => [row.field, row.label, row.value, row.source, row.language ?? null])).toEqual([
      ['titles.sv', 'Title (Swedish)', 'Ge betalaren informationen före en enstaka betalning', 1, 'sv'],
      ['titles.en', 'Title (English)', 'Give the payer the information before a single payment', null, 'en'],
      ['refLabel', 'Reference', '4 kap.', null, null],
      ['summaries.sv', 'Text (Swedish)', 'Innan betalaren blir bunden ska informationen lämnas.', 1, 'sv'],
      ['originalLanguage', 'Original language', 'Swedish', null, null],
      ['instrument', 'Instrument', 'sfs-2010-751', null, null],
      ['dutyType', 'Duty type', 'disclosure', 1, null],
      ['effectiveFrom', 'In force from', '1 May 2010', null, null],
      ['terms', 'Scope', 'regime:payments', 2, null],
    ]);
  });

  it('shows nothing for an empty payload', () => {
    expect(payloadRows({ payload: {}, fieldSources: {}, sourceUrl: '' }, t, defaultFormatContext)).toEqual([]);
  });
});
