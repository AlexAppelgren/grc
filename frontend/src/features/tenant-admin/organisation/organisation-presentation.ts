import type { TaxonomyDimension, TaxonomyTerm } from '@/features/footprint/types';
import type { Licence, OrgUnit, Product } from '@/features/tenant-admin/organisation/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import { problemFrom } from '@/shared/utils/problem';

// Presentation for the organisation screen (design/screens/admin-organisation.html,
// TEN-02). Every pill here sits in the scope block, so every pill is `brand`:
// the legal-entity term, a licence's services, a product's entity and terms.
// Kinds, statuses and dates are plain meta text, because the card adds no pill
// slot for them.

/** The units the legal-entities tree draws; departments have their own section. */
const ENTITY_KINDS: ReadonlySet<OrgUnit['kind']> = new Set(['group', 'legal_entity']);

export interface TreeRow {
  unit: OrgUnit;
  depth: number;
}

/** The group and its legal entities as a tree, flattened in drawing order. A unit whose parent is not in the tree starts one of its own. */
export function entityTree(units: readonly OrgUnit[]): TreeRow[] {
  const entities = units.filter((unit) => ENTITY_KINDS.has(unit.kind));
  const ids = new Set(entities.map((unit) => unit.id));
  const children = new Map<string | null, OrgUnit[]>();
  for (const unit of entities) {
    const parent = unit.parentId !== null && ids.has(unit.parentId) ? unit.parentId : null;
    children.set(parent, [...(children.get(parent) ?? []), unit]);
  }
  const rows: TreeRow[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const unit of children.get(parent) ?? []) {
      rows.push({ unit, depth });
      walk(unit.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

export const legalEntities = (units: readonly OrgUnit[]): OrgUnit[] => units.filter((unit) => unit.kind === 'legal_entity');

/** A certificate is a licence row that carries any of a certificate's own fields. */
export function isCertificate(licence: Licence): boolean {
  return licence.issuer !== '' || licence.number !== '' || licence.scopeStatement !== '' || licence.issuedOn !== null || licence.validUntil !== null || licence.nextAuditOn !== null;
}

/** A row with a withdrawal date reads as withdrawn and stays in the history. */
export const isWithdrawn = (licence: Pick<Licence, 'withdrawnOn'>): boolean => licence.withdrawnOn !== null;

const brand = (key: string, label: string, order: number): PresentedPill => ({ key, label, tone: 'brand', order });

export function presentEntity(unit: Pick<OrgUnit, 'entityTerm'>): PresentedPill[] {
  return unit.entityTerm === null ? [] : [brand(`term:${unit.entityTerm.key}`, unit.entityTerm.label, 0)];
}

export function presentServices(licence: Pick<Licence, 'serviceTerms'>): PresentedPill[] {
  return licence.serviceTerms.map((term, i) => brand(`term:${term.key}`, term.label, i));
}

export function presentProductScope(product: Pick<Product, 'terms'>, unit: Pick<OrgUnit, 'id' | 'name'> | undefined): PresentedPill[] {
  const terms = product.terms.map((term, i) => brand(`term:${term.key}`, term.label, i + 1));
  return unit === undefined ? terms : [brand(`unit:${unit.id}`, unit.name, 0), ...terms];
}

export interface TermGroup {
  dimension: { key: string; label: string };
  terms: TaxonomyTerm[];
}

/**
 * The terms an entity, a licence or a product may carry: those of the dimensions
 * obligations are scoped with (scope and opt-in), never a classification
 * dimension and never a term that mirrors a jurisdiction, which the server refuses.
 */
export function scopeTermGroups(dimensions: readonly TaxonomyDimension[], terms: readonly TaxonomyTerm[], only?: string): TermGroup[] {
  return dimensions
    .filter((d) => (d.kind === 'scope' || d.kind === 'opt_in') && (only === undefined || d.key === only))
    .map((d) => ({ dimension: { key: d.key, label: d.label }, terms: terms.filter((term) => term.dimension === d.key && term.mirrored !== true) }))
    .filter((group) => group.terms.length > 0);
}

export type FieldErrors<F extends string> = Partial<Record<F, string>>;

/**
 * Places a refused write's problem on the fields it names: a 422 lists them in
 * `errors`, and `unknown_member` and `unknown_key` name the one field that can
 * hold a person or a term. What no field takes is left for the form's own alert.
 */
export function fieldErrorsOf<F extends string>(error: unknown, fields: readonly F[], byCode: Partial<Record<string, F>> = {}): { fields: FieldErrors<F>; formLevel: boolean } {
  const problem = problemFrom(error);
  const placed: FieldErrors<F> = {};
  if (problem === null) return { fields: placed, formLevel: error !== null && error !== undefined };
  const byCodeField = byCode[problem.code];
  if (byCodeField !== undefined) {
    placed[byCodeField] = problem.detail;
    return { fields: placed, formLevel: false };
  }
  let unplaced = problem.errors === undefined || problem.errors.length === 0;
  for (const entry of problem.errors ?? []) {
    const record = typeof entry === 'object' && entry !== null ? (entry as Record<string, unknown>) : {};
    const name = typeof record.field === 'string' ? record.field.split('.').pop() : undefined;
    const field = fields.find((f) => f === name);
    if (field !== undefined && typeof record.message === 'string') placed[field] ??= record.message;
    else unplaced = true;
  }
  return { fields: placed, formLevel: unplaced };
}

type Draftable = string | number | boolean | null | readonly string[];

/**
 * The fields of a draft that differ from the row it was opened on: a change
 * sends only those, since the server leaves an omitted or null field alone.
 * A blank date or person means "leave it" too, because a change cannot clear one.
 */
export function changedFields<T extends Record<string, Draftable>>(draft: T, original: Partial<Record<keyof T, Draftable>>, keepBlank: readonly (keyof T)[] = []): Partial<T> {
  const changed: Partial<T> = {};
  for (const key of Object.keys(draft) as (keyof T)[]) {
    const value = draft[key];
    const before = original[key] ?? null;
    if (value === '' && !keepBlank.includes(key)) continue;
    const same = Array.isArray(value) && Array.isArray(before) ? value.join('\u0000') === before.join('\u0000') : value === before;
    if (!same) changed[key] = value;
  }
  return changed;
}

/** A draft's blank strings become the nulls a create leaves out. */
export function orNull(value: string): string | null {
  return value === '' ? null : value;
}
