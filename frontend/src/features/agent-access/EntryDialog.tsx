'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { CheckGroup, CheckRow, Field, Select, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Notice } from '@/components/ui/Notice';
import { ProblemAlert } from '@/components/ui/States';
import { useOrgUnits, useProducts, useRegisterEntry, useUpdateEntry } from '@/features/agent-access/hooks';
import { productsUnder, readsNothing, refusals } from '@/features/agent-access/presentation';
import type { AccessEntry } from '@/features/agent-access/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { problemFrom } from '@/shared/utils/problem';

// Register an agent, or edit one (design/screens/admin-agent-access.html,
// states 3, 4 and 8; ACC-01, ACC-02). The team, departments and products are
// the bank's own rows; naming no department and no product narrows nothing.
// Saving asks for a passkey through the api client. An edit sends If-Match,
// and a stale version renders the 409 in place with a way to load the latest.

interface Draft {
  name: string;
  purpose: string;
  ownerTeam: string;
  departmentIds: string[];
  productIds: string[];
}

type Missing = 'name' | 'purpose' | 'ownerTeam';

function draftOf(entry: AccessEntry | undefined): Draft {
  return {
    name: entry?.name ?? '',
    purpose: entry?.purpose ?? '',
    ownerTeam: entry?.ownerTeam.key ?? '',
    departmentIds: entry?.departments.map((d) => d.id) ?? [],
    productIds: entry?.products.map((p) => p.id) ?? [],
  };
}

const toggled = (ids: string[], id: string, on: boolean): string[] => (on ? [...ids, id] : ids.filter((x) => x !== id));

export function EntryDialog({
  open,
  entry,
  onClose,
  onSaved,
  onReload,
}: {
  open: boolean;
  /** Present when editing; absent when registering. */
  entry?: AccessEntry;
  onClose: () => void;
  onSaved: (entry: AccessEntry) => void;
  /** Refetches the entry after a stale write; the parent remounts the dialog on the new version. */
  onReload?: () => void;
}) {
  const t = useT();
  const register = useRegisterEntry();
  const update = useUpdateEntry();
  const save = entry === undefined ? register : update;
  const teams = useVocabularyValues('team', false, open);
  const units = useOrgUnits(open);
  const products = useProducts(open);
  const [draft, setDraft] = useState<Draft>(() => draftOf(entry));
  const [missing, setMissing] = useState<Missing[]>([]);

  const activeUnits = (units.data ?? []).filter((u) => u.active);
  const liveProducts = (products.data ?? []).filter((p) => p.status !== 'retired');
  const empty = readsNothing(draft, units.data ?? [], products.data ?? []);
  const stale = save.isError && problemFrom(save.error)?.code === 'stale_write';

  const set = (field: keyof Draft, value: Draft[keyof Draft]) => {
    setMissing((current) => current.filter((m) => m !== field));
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const name = draft.name.trim();
    const purpose = draft.purpose.trim();
    const refused: Missing[] = [...(name === '' ? ['name' as const] : []), ...(purpose === '' ? ['purpose' as const] : []), ...(draft.ownerTeam === '' ? ['ownerTeam' as const] : [])];
    setMissing(refused);
    if (refused.length > 0) return;
    const body = { name, purpose, ownerTeam: draft.ownerTeam, departmentIds: draft.departmentIds, productIds: draft.productIds };
    if (entry === undefined) register.mutate(body, { onSuccess: onSaved });
    else update.mutate({ entry, body }, { onSuccess: onSaved });
  };

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : onClose())} title={entry === undefined ? t('agentAccess.dialog.registerTitle') : t('agentAccess.dialog.editTitle', { name: entry.name })}>
      <form onSubmit={submit} noValidate aria-busy={save.isPending} data-entry-form="">
        {stale ? (
          <Notice tone="bad" data-stale="">
            {t('agentAccess.stale')}{' '}
            <Button variant="outline" size="small" onClick={onReload}>
              {t('agentAccess.loadLatest')}
            </Button>
          </Notice>
        ) : null}
        <Field id="entry-name" label={t('agentAccess.field.name')} hint={t('agentAccess.field.nameHint')} error={missing.includes('name') ? t('agentAccess.field.nameRequired') : undefined}>
          <TextInput id="entry-name" maxLength={200} value={draft.name} onChange={(e) => set('name', e.target.value)} aria-invalid={missing.includes('name') ? true : undefined} />
        </Field>
        <Field id="entry-purpose" label={t('agentAccess.field.purpose')} hint={t('agentAccess.field.purposeHint')} error={missing.includes('purpose') ? t('agentAccess.field.purposeRequired') : undefined}>
          <TextArea id="entry-purpose" maxLength={500} value={draft.purpose} onChange={(e) => set('purpose', e.target.value)} aria-invalid={missing.includes('purpose') ? true : undefined} />
        </Field>
        <Field id="entry-team" label={t('agentAccess.field.team')} hint={t('agentAccess.field.teamHint')} error={missing.includes('ownerTeam') ? t('agentAccess.field.teamRequired') : undefined}>
          <Select id="entry-team" value={draft.ownerTeam} onChange={(e) => set('ownerTeam', e.target.value)} aria-invalid={missing.includes('ownerTeam') ? true : undefined}>
            <option value="">{t('agentAccess.field.teamChoose')}</option>
            {(teams.data ?? []).map((team) => (
              <option key={team.key} value={team.key}>
                {team.label}
              </option>
            ))}
          </Select>
        </Field>
        <CheckGroup legend={t('agentAccess.field.departments')} error={units.isError ? t('agentAccess.field.pickerError') : undefined}>
          {units.isSuccess && activeUnits.length === 0 ? <p className="text-meta text-muted">{t('agentAccess.field.pickerEmpty')}</p> : null}
          {activeUnits.map((unit) => {
            const under = productsUnder(unit.id, units.data ?? [], products.data ?? []);
            return (
              <CheckRow
                key={unit.id}
                id={`entry-department-${unit.id}`}
                label={unit.name}
                hint={under.length === 0 ? t('agentAccess.field.noProducts') : under.map((p) => p.name).join(', ')}
                checked={draft.departmentIds.includes(unit.id)}
                onChange={(on) => set('departmentIds', toggled(draft.departmentIds, unit.id, on))}
              />
            );
          })}
        </CheckGroup>
        <CheckGroup legend={t('agentAccess.field.products')} hint={t('agentAccess.field.scopeHint')} error={products.isError ? t('agentAccess.field.pickerError') : undefined}>
          {products.isSuccess && liveProducts.length === 0 ? <p className="text-meta text-muted">{t('agentAccess.field.pickerEmpty')}</p> : null}
          {liveProducts.map((product) => (
            <CheckRow
              key={product.id}
              id={`entry-product-${product.id}`}
              label={product.name}
              checked={draft.productIds.includes(product.id)}
              onChange={(on) => set('productIds', toggled(draft.productIds, product.id, on))}
            />
          ))}
        </CheckGroup>
        {empty ? (
          <Notice tone="warn" data-reads-nothing="">
            {t('agentAccess.field.readsNothing')}
          </Notice>
        ) : null}
        {entry !== undefined ? <p className="text-meta text-muted">{t('agentAccess.dialog.editApplies')}</p> : null}
        {save.isError && !stale ? <ProblemAlert error={save.error} codes={refusals(t)} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={save.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {entry === undefined ? t('agentAccess.dialog.register') : t('agentAccess.dialog.save')}
          </Button>
        </ButtonBar>
        <p className="mt-2 text-meta text-muted">{entry === undefined ? t('agentAccess.registerHint') : t('agentAccess.dialog.saveHint')}</p>
      </form>
    </Modal>
  );
}
