import type { TaxonomyDimension, TaxonomyTerm } from '@/features/footprint/types';
import type { Licence, OrgUnit, Product, RegisterEntry, RegisterLookup, RegisterLookupEntity } from '@/features/tenant-admin/organisation/types';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { MessageKey, Translate } from '@/shared/i18n';
import { formatDate, type FormatContext } from '@/shared/utils/format';
import { problemFrom } from '@/shared/utils/problem';

// Presentation for the organisation screen (design/screens/admin-organisation.html,
// TEN-02). Every pill here sits in the scope block, so every pill is `brand`:
// the legal-entity term, a licence's services, a product's entity and terms.
// Kinds, statuses and dates are plain meta text, because the card adds no pill
// slot for them.

/** The units the legal-entities tree draws; departments have their own section. */
const ENTITY_KINDS: ReadonlySet<OrgUnit['kind']> = new Set(['group', 'legal_entity']);

/** A department is a business area, business unit or function (D-21). */
export const DEPARTMENT_KINDS = ['business_area', 'business_unit', 'function'] as const;
export type DepartmentKind = (typeof DEPARTMENT_KINDS)[number];

export const isDepartment = (unit: Pick<OrgUnit, 'kind'>): boolean => (DEPARTMENT_KINDS as readonly string[]).includes(unit.kind);

/** The departments a team can be put in: the active ones, and the one it sits in already. */
export const teamDepartments = (units: readonly OrgUnit[], current: string | null): OrgUnit[] =>
  units.filter((unit) => isDepartment(unit) && (unit.active || unit.id === current));

export interface TreeRow<U extends OrgUnit = OrgUnit> {
  unit: U;
  depth: number;
}

/** The group and its legal entities as a tree, flattened in drawing order. A unit whose parent is not in the tree starts one of its own. */
export function entityTree<U extends OrgUnit>(units: readonly U[]): TreeRow<U>[] {
  const entities = units.filter((unit) => ENTITY_KINDS.has(unit.kind));
  const ids = new Set(entities.map((unit) => unit.id));
  const children = new Map<string | null, U[]>();
  for (const unit of entities) {
    const parent = unit.parentId !== null && ids.has(unit.parentId) ? unit.parentId : null;
    children.set(parent, [...(children.get(parent) ?? []), unit]);
  }
  const rows: TreeRow<U>[] = [];
  const walk = (parent: string | null, depth: number) => {
    for (const unit of children.get(parent) ?? []) {
      rows.push({ unit, depth });
      walk(unit.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

export const legalEntities = <U extends OrgUnit>(units: readonly U[]): U[] => units.filter((unit) => unit.kind === 'legal_entity');

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

// ——— the public registers (TEN-07; PUBLIC_REGISTERS.md 3.1) ——————————————————————————
// Register wording, names and numbers are data: shown as the register writes them, never
// translated and never kept in a catalog. Only the words around them are ours.

/** A company is ticked when the register licenses it, unless the person flipped it; one the bank already has is always ticked, and is linked rather than added. */
export function isChosen(entity: Pick<RegisterLookupEntity, 'lei' | 'preselected' | 'existingOrgUnitId'>, flipped: ReadonlySet<string>): boolean {
  return entity.existingOrgUnitId !== null || entity.preselected !== flipped.has(entity.lei);
}

/** What applying sends, and what it will do: the chosen LEIs, how many are new and how many the bank already has. */
export function lookupChoice(entities: readonly RegisterLookupEntity[], flipped: ReadonlySet<string>): { leis: string[]; created: number; linked: number } {
  const chosen = entities.filter((entity) => isChosen(entity, flipped));
  const linked = chosen.filter((entity) => entity.existingOrgUnitId !== null).length;
  return { leis: chosen.map((entity) => entity.lei), created: chosen.length - linked, linked };
}

/** The apply button: "Add 2 companies and link 1", "Add 3 companies" or "Link 2 companies". */
export function applyLabel({ created, linked }: { created: number; linked: number }, t: Translate): string {
  if (linked === 0) return t('admin.org.registers.add', { count: created });
  return created === 0 ? t('admin.org.registers.link', { count: linked }) : t('admin.org.registers.addAndLink', { count: created, linked });
}

/** The status line once applied: what was added and what was linked. */
export function appliedMessage({ created, linked }: { created: number; linked: number }, t: Translate): string {
  return [created > 0 ? t('admin.org.registers.added', { count: created }) : '', linked > 0 ? t('admin.org.registers.linked', { count: linked }) : ''].filter((part) => part !== '').join(' ');
}

/** Why a company found has no facts of its own, or that the bank has it already; null for a company the register lists that is new to the bank. */
export function lookupStatus(entity: Pick<RegisterLookupEntity, 'existingOrgUnitId' | 'authority' | 'facts'>, authorityName: string, t: Translate): string | null {
  if (entity.existingOrgUnitId !== null) return t('admin.org.registers.existing');
  if (entity.authority === null) return t('admin.org.registers.noRegister');
  return entity.facts === null ? t('admin.org.registers.notInRegister', { authority: authorityName }) : null;
}

/** "Read from GLEIF and Finansinspektionen's register on 5 Oct 2026.": every register the companies' facts came from, and the day the job read them. */
export function lookupReadLine(lookup: Pick<RegisterLookup, 'completedAt' | 'entities'>, authorityName: (key: string) => string, t: Translate, ctx: FormatContext): string | null {
  if (lookup.completedAt === null) return null;
  const date = formatDate(lookup.completedAt, ctx);
  const registers = [...new Set(lookup.entities.flatMap((entity) => (entity.facts !== null && entity.authority !== null ? [authorityName(entity.authority)] : [])))];
  return registers.length === 0 ? t('admin.org.registers.readFromGleif', { date }) : t('admin.org.registers.readFrom', { authority: registers.join(', '), date });
}

const LOOKUP_ERROR = {
  lookup_not_found: 'admin.org.registers.notFound',
  lookup_ambiguous: 'admin.org.registers.ambiguous',
  register_unavailable: 'admin.org.registers.unavailable',
} as const satisfies Record<NonNullable<RegisterLookup['error']>, MessageKey>;

/** A failed lookup in the screen's own words, by the job's code. */
export function lookupError(code: NonNullable<RegisterLookup['error']>, t: Translate): string {
  return t(LOOKUP_ERROR[code]);
}

/** "Bankaktiebolag · Värdepappersbolag": the register's business names, the main one first. */
export function businessLine(facts: Pick<RegisterEntry['facts'], 'mainBusiness' | 'otherBusinesses'>): string {
  return [facts.mainBusiness, ...facts.otherBusinesses].filter((name) => name !== '').join(' · ');
}

/** "Example Bank AB, filial i Danmark (Danmark)": each branch with its country, as the register names them. */
export function branchesLine(branches: RegisterEntry['facts']['branches'], t: Translate): string {
  return branches.map((branch) => (branch.countryName === '' ? branch.name : t('admin.org.registers.branch', { name: branch.name, country: branch.countryName }))).join(' · ');
}
