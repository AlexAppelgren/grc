'use client';

import type { FormEvent, ReactNode } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { Field, Select } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { ProblemAlert } from '@/components/ui/States';
import type { TermGroup } from '@/features/tenant-admin/organisation/organisation-presentation';
import { usePeople } from '@/features/tenant-admin/organisation/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';

// The pickers the organisation forms share: a term from the dimensions
// obligations are scoped with, several such terms, and a member of the bank.
// Terms and people come as keys and ids with labels from their rows.

function TermOptions({ groups, except = [] }: { groups: readonly TermGroup[]; except?: readonly string[] }) {
  return groups.map((group) => (
    <optgroup key={group.dimension.key} label={group.dimension.label}>
      {group.terms
        .filter((term) => !except.includes(term.key))
        .map((term) => (
          <option key={`${group.dimension.key}:${term.key}`} value={term.key}>
            {term.label}
          </option>
        ))}
    </optgroup>
  ));
}

export function TermSelect({ id, label, hint, error, groups, value, onChange }: { id: string; label: string; hint?: string; error?: string; groups: readonly TermGroup[]; value: string; onChange: (key: string) => void }) {
  const t = useT();
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={error !== undefined}>
        <option value="">{t('admin.org.form.chooseTerm')}</option>
        <TermOptions groups={groups} />
      </Select>
    </Field>
  );
}

/** Several terms: each chosen term is a pressed chip that removes it, and the select below adds one more. */
export function TermPicker({ id, label, hint, error, groups, value, onChange }: { id: string; label: string; hint?: string; error?: string; groups: readonly TermGroup[]; value: readonly string[]; onChange: (keys: string[]) => void }) {
  const t = useT();
  const labelOf = new Map(groups.flatMap((group) => group.terms.map((term) => [term.key, term.label] as const)));
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      {value.length > 0 ? (
        <span className="flex flex-wrap gap-1.5" data-chosen-terms="">
          {value.map((key) => (
            <Chip key={key} pressed onClick={() => onChange(value.filter((k) => k !== key))}>
              <span aria-label={t('admin.org.form.removeTerm', { label: labelOf.get(key) ?? key })}>{labelOf.get(key) ?? key}</span>
            </Chip>
          ))}
        </span>
      ) : null}
      <Select id={id} value="" onChange={(e) => e.target.value !== '' && onChange([...value, e.target.value])} aria-invalid={error !== undefined}>
        <option value="">{t('admin.org.form.addTerm')}</option>
        <TermOptions groups={groups} except={value} />
      </Select>
    </Field>
  );
}

/** A member of the bank, from the people picker; the current choice stays listed while the list loads. */
export function PersonSelect({ id, label, hint, error, value, current, onChange }: { id: string; label: string; hint?: string; error?: string; value: string; current: { id: string; name: string } | null; onChange: (userId: string) => void }) {
  const t = useT();
  const people = usePeople();
  const options = people.data ?? (current === null ? [] : [current]);
  return (
    <Field id={id} label={label} hint={hint} error={error}>
      <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} aria-invalid={error !== undefined} aria-busy={people.isPending}>
        {/* Nobody is where a new row starts; a patch cannot clear an owner, so it is not offered once there is one. */}
        <option value="" disabled={current !== null}>
          {t('admin.org.form.nobody')}
        </option>
        {options.map((person) => (
          <option key={person.id} value={person.id}>
            {person.name}
          </option>
        ))}
      </Select>
    </Field>
  );
}

/**
 * The dialog every organisation form sits in. A refused write shows here
 * unless its fields took it; a stale write gets the screen's own sentence,
 * and the list behind the dialog has already refetched the row as it stands.
 */
export function DialogForm({ title, error, formLevel, pending, onSubmit, onClose, children }: { title: string; error: unknown; formLevel: boolean; pending: boolean; onSubmit: () => void; onClose: () => void; children: ReactNode }) {
  const t = useT();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title={title}>
      <form onSubmit={submit} noValidate aria-busy={pending}>
        {children}
        {formLevel ? <ProblemAlert error={error} codes={{ stale_write: t('admin.org.form.stale') }} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={pending}>
            {t('common.save')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}
