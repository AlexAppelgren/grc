'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert } from '@/components/ui/States';
import { useAddInternalLink, useInternalItems, useInternalLinks, useRemoveInternalLink } from '@/features/register/hooks';
import type { RegisterInternalItemPage, RegisterInternalLink, RegisterInternalLinkBody } from '@/features/register/types';
import { useVocabularyValues } from '@/features/vocabularies/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { cn } from '@/shared/utils/cn';
import { externalHref } from '@/shared/utils/external-href';

// "Linked internal items" (REG-05; design/screens/tenant-obligation.html): the
// bank's own policies, procedures and controls that carry the duty, each with
// its kind and the reference its GRC system knows it by. A member holding
// register.edit links one, picked from the bank's items or created in the same
// call, and removes a link; the item itself stays. Kinds are the bank's
// `link_kind` rows: the screen shows their labels and sends their keys.

const EDIT_PERMISSION = 'register.edit';
type Item = RegisterInternalItemPage['items'][number];

function LinkDialog({ obligationId, onOpenChange }: { obligationId: string; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const [mode, setMode] = useState<'pick' | 'create'>('pick');
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<Item | null>(null);
  const [kind, setKind] = useState('');
  const [name, setName] = useState('');
  const [reference, setReference] = useState('');
  const [url, setUrl] = useState('');
  const items = useInternalItems(query.trim(), mode === 'pick');
  const kinds = useVocabularyValues('link_kind', false, mode === 'create');
  const add = useAddInternalLink(obligationId);
  const kindOptions = kinds.data ?? [];
  const chosenKind = kind === '' ? (kindOptions[0]?.key ?? '') : kind;

  const switchTo = (next: 'pick' | 'create') => {
    add.reset();
    setMode(next);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    // The reference the bank knows the item by is what the list shows beside it.
    let body: RegisterInternalLinkBody;
    if (mode === 'pick') {
      if (picked === null) return;
      body = { kind: picked.kind.key, label: picked.name, internalItemId: picked.id, externalRef: picked.reference };
    } else {
      const ref = reference.trim() === '' ? null : reference.trim();
      body = { kind: chosenKind, label: name.trim(), reference: ref, externalRef: ref, url: url.trim() === '' ? null : url.trim() };
    }
    add.mutate(body, { onSuccess: () => onOpenChange(false) });
  };

  const refusals = {
    already_linked: t('obligationLinks.alreadyLinked'),
    duplicate_key: t('obligationLinks.duplicate'),
    unknown_key: t('obligationLinks.unknownKind'),
  };
  const ready = mode === 'pick' ? picked !== null : chosenKind !== '' && name.trim() !== '';

  return (
    <Modal open onOpenChange={onOpenChange} title={t(mode === 'pick' ? 'obligationLinks.pickTitle' : 'obligationLinks.createTitle')}>
      <form onSubmit={submit} noValidate aria-busy={add.isPending} data-link-dialog={mode}>
        {mode === 'pick' ? (
          <>
            <Field id="link-find" label={t('obligationLinks.find')}>
              <TextInput id="link-find" type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
            </Field>
            {items.isPending ? (
              <LoadingState rows={1} />
            ) : items.isError ? (
              <ProblemAlert error={items.error} />
            ) : items.data.items.length === 0 ? (
              <p className="text-meta text-muted">{t('obligationLinks.noMatch')}</p>
            ) : (
              <Rows role="radiogroup" aria-label={t('obligationLinks.find')}>
                {items.data.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="radio"
                    aria-checked={picked?.id === item.id}
                    onClick={() => setPicked(item)}
                    className={cn('rounded-card border px-4 py-3 text-left', picked?.id === item.id ? 'border-fg' : 'border-line')}
                    data-pick-item={item.id}
                  >
                    <Meta>
                      <span>{item.kind.label}</span>
                      {item.reference === null ? null : <span className="font-mono">{item.reference}</span>}
                    </Meta>
                    <h3>{item.name}</h3>
                  </button>
                ))}
              </Rows>
            )}
            <ButtonBar className="justify-start">
              <Button variant="ghost" size="small" onClick={() => switchTo('create')}>
                {t('obligationLinks.createInstead')}
              </Button>
            </ButtonBar>
          </>
        ) : (
          <>
            <Field id="link-kind" label={t('obligationLinks.kind')}>
              <Select id="link-kind" value={chosenKind} onChange={(event) => setKind(event.target.value)}>
                {kindOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </Field>
            <Field id="link-name" label={t('obligationLinks.name')}>
              <TextInput id="link-name" value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field id="link-reference" label={t('obligationLinks.reference')}>
              <TextInput id="link-reference" value={reference} onChange={(event) => setReference(event.target.value)} />
            </Field>
            <Field id="link-url" label={t('obligationLinks.url')} hint={t('obligationLinks.urlHint')}>
              <TextInput id="link-url" type="url" inputMode="url" value={url} onChange={(event) => setUrl(event.target.value)} />
            </Field>
          </>
        )}
        {add.isError ? <ProblemAlert error={add.error} codes={refusals} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={() => (mode === 'create' ? switchTo('pick') : onOpenChange(false))}>
            {t(mode === 'create' ? 'common.back' : 'common.cancel')}
          </Button>
          <Button type="submit" disabled={!ready || add.isPending}>
            {t(mode === 'pick' ? 'obligationLinks.link' : 'obligationLinks.createAndLink')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function RemoveDialog({ link, onOpenChange }: { link: RegisterInternalLink; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const remove = useRemoveInternalLink();
  return (
    <Modal open onOpenChange={onOpenChange} title={t('obligationLinks.removeTitle', { name: link.label })} description={t('obligationLinks.removeBody')}>
      {remove.isError ? <ProblemAlert error={remove.error} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          {t('common.cancel')}
        </Button>
        <Button disabled={remove.isPending} onClick={() => remove.mutate(link.id, { onSuccess: () => onOpenChange(false) })}>
          {t('obligationLinks.removeConfirm')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

function LinkRow({ link, onRemove }: { link: RegisterInternalLink; onRemove: (() => void) | null }) {
  const t = useT();
  const href = link.url === null ? null : externalHref(link.url);
  return (
    <Row data-link-id={link.id}>
      <Meta>
        <span data-link-kind="">{link.kind.label}</span>
        {link.externalRef === null ? null : (
          <span className="font-mono" data-link-ref="">
            {link.externalRef}
          </span>
        )}
      </Meta>
      <h3 className="mt-1">
        {href === null ? (
          link.label
        ) : (
          <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
            {link.label}
          </a>
        )}
      </h3>
      {onRemove === null ? null : (
        <Button variant="ghost" size="small" className="mt-2" onClick={onRemove}>
          {t('obligationLinks.remove')}
        </Button>
      )}
    </Row>
  );
}

export function ObligationLinksPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const canEdit = (usePermissions() ?? []).includes(EDIT_PERMISSION);
  const links = useInternalLinks(obligationId);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<RegisterInternalLink | null>(null);
  const items = links.data?.items ?? [];
  const total = links.data?.total ?? 0;

  return (
    <Panel title={t('obligationLinks.heading')} data-links-panel="">
      {links.isPending ? (
        <LoadingState rows={1} />
      ) : links.isError ? (
        <ErrorState title={t('obligationLinks.errorTitle')} onRetry={() => void links.refetch()} />
      ) : items.length === 0 ? (
        <p className="text-meta text-muted" data-links-empty="">
          {t('obligationLinks.empty')}
        </p>
      ) : (
        <>
          <Rows>
            {items.map((link) => (
              <LinkRow key={link.id} link={link} onRemove={canEdit ? () => setRemoving(link) : null} />
            ))}
          </Rows>
          {total > items.length ? <Meta className="mt-3">{t('obligationLinks.more', { shown: items.length, total })}</Meta> : null}
        </>
      )}
      {canEdit ? (
        <ButtonBar>
          <Button size="small" onClick={() => setAdding(true)}>
            {t('obligationLinks.add')}
          </Button>
        </ButtonBar>
      ) : null}
      {adding ? <LinkDialog obligationId={obligationId} onOpenChange={setAdding} /> : null}
      {removing === null ? null : <RemoveDialog link={removing} onOpenChange={(open) => (open ? undefined : setRemoving(null))} />}
    </Panel>
  );
}
