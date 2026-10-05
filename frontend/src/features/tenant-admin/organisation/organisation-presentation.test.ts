import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it } from 'vitest';

import type { TaxonomyDimension, TaxonomyTerm } from '@/features/footprint/types';

import { createT } from '@/shared/i18n';
import { defaultFormatContext, formatDate } from '@/shared/utils/format';

import {
  appliedMessage,
  applyLabel,
  branchesLine,
  businessLine,
  changedFields,
  entityTree,
  fieldErrorsOf,
  isCertificate,
  isChosen,
  isWithdrawn,
  lookupChoice,
  lookupError,
  lookupReadLine,
  lookupStatus,
  presentEntity,
  presentProductScope,
  presentServices,
  scopeTermGroups,
} from './organisation-presentation';
import type { Licence, OrgUnit, RegisterLookupEntity } from './types';

// The organisation screen's presentation (TEN-02): the entity tree, the one
// pill slot (brand, the scope block), which fields a refused write names, and
// what a change sends.

function unit(id: string, kind: OrgUnit['kind'], parentId: string | null = null): OrgUnit {
  return { id, kind, name: id, parentId, orgNumber: '', lei: '', countryCode: '', entityTerm: null, head: null, active: true, version: 1 };
}

const licence: Licence = {
  id: 'l1',
  orgUnitId: 'bank',
  licenceType: { key: 'bank', kind: null, label: 'Bank' },
  reference: 'FI 12-3456',
  grantedOn: '2014-03-01',
  withdrawnOn: null,
  scopeNote: '',
  issuer: '',
  number: '',
  scopeStatement: '',
  issuedOn: null,
  validUntil: null,
  nextAuditOn: null,
  owner: null,
  serviceTerms: [{ key: 'custody', kind: null, label: 'Custody' }],
  version: 1,
};

function problem(status: number, data: Record<string, unknown>): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  return new AxiosError('refused', String(status), config, undefined, { data, status, statusText: '', headers: {}, config });
}

describe('the legal-entity tree', () => {
  it('draws the group with its entities under it and leaves departments to their own section', () => {
    const rows = entityTree([unit('bank', 'legal_entity', 'group'), unit('retail', 'business_area', 'bank'), unit('group', 'group'), unit('fonder', 'legal_entity', 'group'), unit('loose', 'legal_entity', 'retail')]);
    expect(rows.map((row) => [row.unit.id, row.depth])).toEqual([
      ['group', 0],
      ['bank', 1],
      ['fonder', 1],
      // Its parent is a department, which this tree does not draw: it starts a tree of its own.
      ['loose', 0],
    ]);
  });
});

describe('licences and certificates', () => {
  it('reads a row as a certificate once it carries any certificate field, and as withdrawn once it has a date', () => {
    expect(isCertificate(licence)).toBe(false);
    expect(isCertificate({ ...licence, issuer: 'Example Certification AB' })).toBe(true);
    expect(isCertificate({ ...licence, nextAuditOn: '2027-03-10' })).toBe(true);
    expect(isWithdrawn(licence)).toBe(false);
    expect(isWithdrawn({ ...licence, withdrawnOn: '2026-01-31' })).toBe(true);
  });
});

describe('the scope block', () => {
  it('shows every term, a licence service and a product entity as a brand pill', () => {
    expect(presentEntity({ entityTerm: { key: 'bank', kind: null, label: 'Bank' } })).toEqual([{ key: 'term:bank', label: 'Bank', tone: 'brand', order: 0 }]);
    expect(presentEntity({ entityTerm: null })).toEqual([]);
    expect(presentServices(licence).map((pill) => [pill.label, pill.tone])).toEqual([['Custody', 'brand']]);
    const product = { terms: [{ key: 'isk', kind: null, label: 'ISK' }] };
    expect(presentProductScope(product, { id: 'bank', name: 'Example Bank AB' }).map((pill) => [pill.label, pill.tone])).toEqual([
      ['Example Bank AB', 'brand'],
      ['ISK', 'brand'],
    ]);
    expect(presentProductScope(product, undefined).map((pill) => pill.label)).toEqual(['ISK']);
  });

  it('offers only the terms of the dimensions obligations are scoped with, never a mirrored one', () => {
    const dimensions: TaxonomyDimension[] = [
      { key: 'service_type', kind: 'scope', label: 'Services', restrictsFootprint: true },
      { key: 'standard', kind: 'opt_in', label: 'Standards', restrictsFootprint: false },
      { key: 'topic', kind: 'classification', label: 'Topics', restrictsFootprint: false },
      { key: 'jurisdiction', kind: 'scope', label: 'Markets', restrictsFootprint: true },
    ];
    const terms: TaxonomyTerm[] = [
      { dimension: 'service_type', key: 'custody', kind: null, label: 'Custody' },
      { dimension: 'standard', key: 'iso_iec_27001', kind: null, label: 'ISO/IEC 27001' },
      { dimension: 'topic', key: 'aml', kind: null, label: 'AML' },
      { dimension: 'jurisdiction', key: 'se', kind: null, label: 'Sweden', mirrored: true },
    ];
    expect(scopeTermGroups(dimensions, terms).map((group) => [group.dimension.key, group.terms.map((term) => term.key)])).toEqual([
      ['service_type', ['custody']],
      ['standard', ['iso_iec_27001']],
    ]);
    expect(scopeTermGroups(dimensions, terms, 'standard').map((group) => group.dimension.key)).toEqual(['standard']);
  });
});

describe('a refused write', () => {
  const fields = ['name', 'ownerUserId', 'terms'] as const;

  it('puts each 422 error on the field it names and keeps the rest for the form', () => {
    const refused = problem(422, { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.body.name', message: 'Too long.' }] });
    expect(fieldErrorsOf(refused, fields)).toEqual({ fields: { name: 'Too long.' }, formLevel: false });
    const elsewhere = problem(422, { code: 'validation_error', detail: 'Some fields need attention.', errors: [{ field: 'body.body.colour', message: 'Extra.' }] });
    expect(fieldErrorsOf(elsewhere, fields)).toEqual({ fields: {}, formLevel: true });
  });

  it('puts unknown_member and unknown_key on the field that holds a person or a term', () => {
    const member = problem(422, { code: 'unknown_member', detail: 'That person is not an active member of your organisation.' });
    expect(fieldErrorsOf(member, fields, { unknown_member: 'ownerUserId', unknown_key: 'terms' })).toEqual({ fields: { ownerUserId: 'That person is not an active member of your organisation.' }, formLevel: false });
    const term = problem(422, { code: 'unknown_key', detail: 'Not a term obligations are scoped with: nope.' });
    expect(fieldErrorsOf(term, fields, { unknown_member: 'ownerUserId', unknown_key: 'terms' }).fields).toEqual({ terms: 'Not a term obligations are scoped with: nope.' });
  });

  it('leaves a stale write, and anything without fields, to the form', () => {
    expect(fieldErrorsOf(problem(409, { code: 'stale_write', detail: 'Changed.' }), fields)).toEqual({ fields: {}, formLevel: true });
    expect(fieldErrorsOf(null, fields)).toEqual({ fields: {}, formLevel: false });
    expect(fieldErrorsOf(undefined, fields)).toEqual({ fields: {}, formLevel: false });
  });

  it('leaves an error that is not a problem answer, such as a thrown one, to the form', () => {
    expect(fieldErrorsOf(new Error('boom'), fields)).toEqual({ fields: {}, formLevel: true });
  });

  it('keeps for the form a 422 entry that is not an object or names no field, and still places the ones that do', () => {
    const refused = problem(422, { code: 'validation_error', detail: 'Some fields need attention.', errors: ['Too long.', { field: 3, message: 'No name.' }, { field: 'body.body.name', message: 'Too long.' }] });
    expect(fieldErrorsOf(refused, fields)).toEqual({ fields: { name: 'Too long.' }, formLevel: true });
    const unnamed = problem(422, { code: 'validation_error', detail: 'Some fields need attention.', errors: [null] });
    expect(fieldErrorsOf(unnamed, fields)).toEqual({ fields: {}, formLevel: true });
  });
});

describe('a change', () => {
  it('sends only what moved, never a blank date or person, and a blank text only where asked', () => {
    const before = { name: 'Custody', description: 'Old', launchDate: '2012-03-01', ownerUserId: 'u1', terms: ['custody'] };
    expect(changedFields({ name: 'Custody', description: '', launchDate: '', ownerUserId: 'u2', terms: ['custody', 'isk'] }, before, ['description'])).toEqual({
      description: '',
      ownerUserId: 'u2',
      terms: ['custody', 'isk'],
    });
    expect(changedFields({ name: 'Custody', description: 'Old', launchDate: '2012-03-01', ownerUserId: 'u1', terms: ['custody'] }, before)).toEqual({});
  });
});

describe('the public registers (TEN-07)', () => {
  const t = createT('en');
  const sv = createT('sv');
  const facts = {
    name: 'Example Bank AB',
    registrationNumber: '556000-0001',
    lei: '549300EXAMPLEBANK001',
    mainBusiness: 'Bankaktiebolag',
    otherBusinesses: ['Värdepappersbolag', 'Försäkringsdistribution'],
    licences: [{ text: 'Tillstånd att driva bankrörelse', grantedOn: '1995-03-01' }],
    branches: [
      { name: 'Example Bank AB, filial i Danmark', countryName: 'Danmark', jurisdiction: 'dk' },
      { name: 'Example Bank AB, filial i Ukraina', countryName: '', jurisdiction: null },
    ],
    listed: true,
  };
  const company = (lei: string, overrides: Partial<RegisterLookupEntity> = {}): RegisterLookupEntity => ({
    lei,
    name: lei,
    registrationNumber: '',
    country: 'SE',
    parentLei: null,
    leiStatus: 'ISSUED',
    authority: 'fi',
    facts,
    existingOrgUnitId: null,
    preselected: true,
    unmapped: [],
    entityType: null,
    sourceUrl: null,
    ...overrides,
  });
  const bank = company('bank', { existingOrgUnitId: 'u-bank' });
  const fonder = company('fonder');
  const holding = company('holding', { facts: null, preselected: false });
  const pank = company('pank', { authority: null, facts: null, preselected: false, country: 'EE' });

  it('ticks what the register licenses and what the bank has, lets a person flip the rest, and never unticks the bank\'s own', () => {
    const none = new Set<string>();
    expect([bank, fonder, holding, pank].map((entity) => isChosen(entity, none))).toEqual([true, true, false, false]);
    const flipped = new Set(['bank', 'fonder', 'holding']);
    expect([bank, fonder, holding, pank].map((entity) => isChosen(entity, flipped))).toEqual([true, false, true, false]);
    expect(lookupChoice([bank, fonder, holding, pank], none)).toEqual({ leis: ['bank', 'fonder'], created: 1, linked: 1 });
    expect(lookupChoice([bank, fonder, holding, pank], new Set(['fonder', 'holding']))).toEqual({ leis: ['bank', 'holding'], created: 1, linked: 1 });
  });

  it('says what applying adds and links, and what it did', () => {
    expect(applyLabel({ created: 2, linked: 1 }, t)).toBe('Add 2 companies and link 1');
    expect(applyLabel({ created: 1, linked: 0 }, t)).toBe('Add 1 company');
    expect(applyLabel({ created: 0, linked: 2 }, t)).toBe('Link 2 companies');
    expect(applyLabel({ created: 3, linked: 0 }, sv)).toBe('Lägg till 3 bolag');
    expect(appliedMessage({ created: 2, linked: 1 }, t)).toBe('Added 2 companies from the public registers. Linked 1 company you already had.');
    expect(appliedMessage({ created: 1, linked: 0 }, t)).toBe('Added 1 company from the public registers.');
    expect(appliedMessage({ created: 0, linked: 2 }, t)).toBe('Linked 2 companies you already had.');
  });

  it('says why a company has no facts, or that the bank has it already', () => {
    expect(lookupStatus(bank, 'Finansinspektionen', t)).toBe('Already in your organisation');
    expect(lookupStatus(fonder, 'Finansinspektionen', t)).toBeNull();
    expect(lookupStatus(holding, 'Finansinspektionen', t)).toBe("Not in Finansinspektionen's register");
    expect(lookupStatus(pank, '', t)).toBe('No register we read for this country');
    expect(lookupStatus(holding, 'Finansinspektionen', sv)).toBe('Finns inte i registret hos Finansinspektionen');
  });

  it('says a failed lookup in the screen\'s own words, by its code', () => {
    expect(lookupError('lookup_not_found', t)).toBe('No company has that number. Check it, or type the LEI.');
    expect(lookupError('lookup_ambiguous', t)).toBe('More than one company has that number. Type the LEI instead.');
    expect(lookupError('register_unavailable', t)).toBe('The register could not be read. Try again later.');
  });

  it('names the registers read and the day, once each', () => {
    const name = (key: string) => (key === 'fi' ? 'Finansinspektionen' : key);
    const done = { completedAt: '2026-10-05T08:00:04Z', entities: [bank, fonder, holding, pank] };
    expect(lookupReadLine(done, name, t, defaultFormatContext)).toBe(`Read from GLEIF and Finansinspektionen's register on ${formatDate(done.completedAt, defaultFormatContext)}.`);
    expect(lookupReadLine({ ...done, entities: [holding, pank] }, name, t, defaultFormatContext)).toBe(`Read from GLEIF on ${formatDate(done.completedAt, defaultFormatContext)}.`);
    expect(lookupReadLine({ ...done, completedAt: null }, name, t, defaultFormatContext)).toBeNull();
  });

  it('writes the register\'s businesses and branches as the register does', () => {
    expect(businessLine(facts)).toBe('Bankaktiebolag · Värdepappersbolag · Försäkringsdistribution');
    expect(businessLine({ mainBusiness: '', otherBusinesses: ['Fondbolag'] })).toBe('Fondbolag');
    expect(branchesLine(facts.branches, t)).toBe('Example Bank AB, filial i Danmark (Danmark) · Example Bank AB, filial i Ukraina');
  });
});
