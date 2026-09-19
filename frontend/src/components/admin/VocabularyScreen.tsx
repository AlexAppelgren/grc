'use client';

import { useMemo, useState, type FormEvent, type KeyboardEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Chip, ChipRow } from '@/components/ui/Chip';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Meta, Panel, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { SwatchPair } from '@/components/ui/Swatch';
import {
  useCreateValue,
  useMergeValue,
  usePreviewMerge,
  useReorderValues,
  useRestoreValue,
  useRetireValue,
  useUpdateValue,
  useVocabularies,
  useVocabularyValues,
} from '@/features/vocabularies/hooks';
import type { VocabularyRow } from '@/features/vocabularies/types';
import {
  IN_USE_CODE,
  exactDuplicateFrom,
  listLabel,
  nearDuplicateFrom,
  presentVocabularyRow,
  presentVocabularyValue,
  usageText,
} from '@/features/vocabularies/vocabulary-presentation';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';

// /admin/vocabularies/[list]: one vocabulary
// (design/screens/admin-vocabulary.html; VOC-01, VOC-02, VOC-07, AC-VOC1,
// AC-VOC2, AC-VOC3). Each row shows the value as the real pill in a light and
// a dark swatch, with its key, usage count and usage note.
//
// The two tiers behave differently. A TENANT list is edited here directly by
// a holder of `vocab.manage`. A LIBRARY list is VOC-07: every write answers
// 202 with the proposal it created, confirmed where it was sent, and the
// platform console reviews it. Tone is
// never chosen on this screen: it comes from the list's slot or the row's
// fixed kind.

const ACTIVE = 'active';
const RETIRED = 'retired';
// A library-list write is a proposal, and proposing needs this grant (VOC-07).
const PROPOSALS_CREATE = 'proposals.create';

/** The drag handle's glyph: an icon, not copy, so it is not in the catalog. */
const GRIP_GLYPH = '⋮⋮';

/** The order a drag or an arrow key produces, as the reorder call wants it. */
export function moveKey(keys: readonly string[], key: string, to: number): string[] {
  const from = keys.indexOf(key);
  if (from === -1) return [...keys];
  const target = Math.max(0, Math.min(keys.length - 1, to));
  const next = [...keys];
  next.splice(from, 1);
  next.splice(target, 0, key);
  return next;
}

function labelsOf(en: string, sv: string): Record<string, string> {
  return sv.trim() === '' ? { en: en.trim() } : { en: en.trim(), sv: sv.trim() };
}

// ——— inline rename ————————————————————————————————————————————————

function RenameForm({ list, row, isLibrary, onClose }: { list: string; row: VocabularyRow; isLibrary: boolean; onClose: () => void }) {
  const t = useT();
  const update = useUpdateValue(list);
  const [labelEn, setLabelEn] = useState(row.labels.en ?? row.label);
  const [labelSv, setLabelSv] = useState(row.labels.sv ?? '');
  const [blank, setBlank] = useState(false);
  const [proposed, setProposed] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (labelEn.trim() === '') {
      setBlank(true);
      return;
    }
    setBlank(false);
    update.mutate(
      { key: row.key, body: { labels: labelsOf(labelEn, labelSv) }, version: row.version },
      {
        onSuccess: (write) => {
          if (write.outcome === 'proposed') setProposed(write.proposal.title);
          else onClose();
        },
      },
    );
  };

  if (proposed !== null) {
    return (
      <div className="grid gap-1.5" data-rename-proposed="">
        <StatusLine tone="positive">{t('admin.vocabularies.proposed', { title: proposed })}</StatusLine>
        <ButtonBar>
          <Button variant="outline" size="small" onClick={onClose}>
            {t('common.done')}
          </Button>
        </ButtonBar>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate aria-busy={update.isPending} data-rename-form={row.key} className="grid gap-1.5">
      <Field id={`rename-en-${row.key}`} label={t('admin.vocabularies.newLabel')} error={blank ? t('admin.vocabularies.labelRequired') : undefined}>
        <TextInput id={`rename-en-${row.key}`} value={labelEn} autoFocus onChange={(e) => setLabelEn(e.target.value)} />
      </Field>
      <Field id={`rename-sv-${row.key}`} label={t('admin.vocabularies.labelSv')} hint={t('admin.vocabularies.labelSvHint')}>
        <TextInput id={`rename-sv-${row.key}`} placeholder={t('admin.vocabularies.labelSvPlaceholder')} value={labelSv} onChange={(e) => setLabelSv(e.target.value)} />
      </Field>
      <small className="text-meta text-muted">{t('admin.vocabularies.keyKept', { key: row.key })}</small>
      {update.isError ? <ProblemAlert error={update.error} /> : null}
      <ButtonBar>
        <Button variant="outline" size="small" onClick={onClose} disabled={update.isPending}>
          {t('common.cancel')}
        </Button>
        <Button type="submit" size="small" disabled={update.isPending}>
          {isLibrary ? t('admin.vocabularies.sendForReview') : t('common.save')}
        </Button>
      </ButtonBar>
    </form>
  );
}

// ——— one row ——————————————————————————————————————————————————————

function ValueRow({
  list,
  row,
  index,
  count,
  isLibrary,
  readOnly,
  editing,
  onEdit,
  onRetire,
  onMerge,
  onMove,
  onDragStart,
  onDrop,
}: {
  list: string;
  row: VocabularyRow;
  index: number;
  count: number;
  isLibrary: boolean;
  readOnly: boolean;
  editing: boolean;
  onEdit: (key: string | null) => void;
  onRetire: (row: VocabularyRow) => void;
  onMerge: (row: VocabularyRow) => void;
  onMove: (key: string, to: number) => void;
  onDragStart: (key: string) => void;
  onDrop: (index: number) => void;
}) {
  const t = useT();
  const restore = useRestoreValue(list);
  const pill = presentVocabularyValue(list, row);
  const markers = presentVocabularyRow(list, row, t);
  const reorderable = row.active && !isLibrary && count > 1;

  const onGripKey = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      onMove(row.key, index - 1);
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      onMove(row.key, index + 1);
    }
  };

  return (
    <div
      className={
        row.active
          ? 'grid grid-cols-[auto_1fr] items-start gap-x-3 gap-y-2 rounded-card border border-line bg-surface px-4 py-3 md:grid-cols-[auto_1fr_auto]'
          : 'grid grid-cols-[auto_1fr] items-start gap-x-3 gap-y-2 rounded-card border border-dashed border-line bg-surface px-4 py-3 opacity-60 md:grid-cols-[auto_1fr_auto]'
      }
      data-value-key={row.key}
      data-value-active={row.active ? '' : undefined}
      draggable={reorderable}
      onDragStart={() => onDragStart(row.key)}
      onDragOver={(event) => event.preventDefault()}
      onDrop={() => onDrop(index)}
    >
      {reorderable ? (
        <span
          role="button"
          tabIndex={0}
          aria-label={t('admin.vocabularies.dragToReorder')}
          onKeyDown={onGripKey}
          className="cursor-grab leading-none text-muted select-none"
          data-grip={row.key}
        >
          {GRIP_GLYPH}
        </span>
      ) : (
        <span aria-hidden="true" className="w-3.5" />
      )}

      <div className="min-w-0">
        {editing ? (
          <RenameForm list={list} row={row} isLibrary={isLibrary} onClose={() => onEdit(null)} />
        ) : (
          <>
            <SwatchPair>
              <PillRow pills={[pill]} />
            </SwatchPair>
            <Meta className="mt-1.5">
              <code className="font-mono">{row.key}</code>
              <PillRow pills={markers} />
            </Meta>
            <small className="mt-1 block text-meta text-muted">{usageText(row.usageCount, t)}</small>
            {row.usageNote.length > 0 ? <small className="block text-meta text-muted">{row.usageNote}</small> : null}
          </>
        )}
        {restore.isError ? <ProblemAlert error={restore.error} /> : null}
      </div>

      {editing || readOnly ? null : (
        <div className="col-span-2 md:col-span-1">
          <ButtonBar className="mt-0">
            {!row.active ? (
              <Button variant="outline" size="small" disabled={restore.isPending} onClick={() => restore.mutate(row.key)}>
                {t('admin.vocabularies.restore')}
              </Button>
            ) : (
              <>
                {row.isSystem ? null : (
                  <Button variant="danger" size="small" onClick={() => onRetire(row)}>
                    {t('admin.vocabularies.retire')}
                  </Button>
                )}
                {row.isSystem ? null : (
                  <Button variant="outline" size="small" onClick={() => onMerge(row)}>
                    {t('admin.vocabularies.mergeInto')}
                  </Button>
                )}
                <Button variant="outline" size="small" onClick={() => onEdit(row.key)}>
                  {t('admin.vocabularies.rename')}
                </Button>
              </>
            )}
          </ButtonBar>
        </div>
      )}
    </div>
  );
}

// ——— retire ———————————————————————————————————————————————————————

function RetireDialog({ list, row, onClose }: { list: string; row: VocabularyRow; onClose: () => void }) {
  const t = useT();
  const retire = useRetireValue(list);
  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('admin.vocabularies.retireTitle', { label: row.label })}
      description={row.usageCount === 0 ? t('admin.vocabularies.retireBodyUnused') : t('admin.vocabularies.retireBodyUsed', { count: row.usageCount })}
    >
      {retire.isError ? <ProblemAlert error={retire.error} codes={{ [IN_USE_CODE]: t('admin.vocabularies.retireBodyUsed', { count: row.usageCount }) }} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={onClose} disabled={retire.isPending}>
          {t('common.cancel')}
        </Button>
        <Button variant="danger" disabled={retire.isPending} onClick={() => retire.mutate({ key: row.key, confirm: true }, { onSuccess: onClose })}>
          {t('admin.vocabularies.retire')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}

// ——— merge ————————————————————————————————————————————————————————

function MergeDialog({ list, row, targets, onClose }: { list: string; row: VocabularyRow; targets: readonly VocabularyRow[]; onClose: () => void }) {
  const t = useT();
  const preview = usePreviewMerge(list);
  const merge = useMergeValue(list);
  const [into, setInto] = useState(targets[0]?.key ?? '');
  const [proposed, setProposed] = useState<string | null>(null);
  const target = targets.find((candidate) => candidate.key === into);
  const moved = preview.data?.moved;

  const runPreview = (key: string) => {
    setInto(key);
    if (key !== '') preview.mutate({ key: row.key, into: key });
  };

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('admin.vocabularies.mergeTitle', { label: row.label })}
    >
      <Field id="merge-into" label={t('admin.vocabularies.mergeKeep')}>
        <select id="merge-into" className="h-9 w-full rounded-control border border-line-strong bg-surface px-2.5" value={into} onChange={(e) => runPreview(e.target.value)}>
          {targets.map((candidate) => (
            <option key={candidate.key} value={candidate.key}>
              {candidate.label}
            </option>
          ))}
        </select>
      </Field>

      {proposed !== null ? (
        <StatusLine tone="positive">{t('admin.vocabularies.proposed', { title: proposed })}</StatusLine>
      ) : (
        <>
          <Panel title={t('admin.vocabularies.mergeWhatHappens')} data-merge-preview="">
            {preview.isPending ? (
              <StatusLine>{t('common.loading')}</StatusLine>
            ) : moved === undefined ? (
              <StatusLine>{t('admin.vocabularies.mergePickTarget')}</StatusLine>
            ) : (
              <>
                <p>{t('admin.vocabularies.mergeMoves', { count: moved, from: row.label, into: target?.label ?? into })}</p>
                <p className="mt-1.5">{t('admin.vocabularies.mergeRetires', { label: row.label })}</p>
                <p className="mt-1.5 text-meta text-muted">{t('admin.vocabularies.mergeAudit')}</p>
              </>
            )}
            {preview.isError ? <ProblemAlert error={preview.error} /> : null}
          </Panel>
          {merge.isError ? <ProblemAlert error={merge.error} /> : null}
        </>
      )}

      <ButtonBar>
        <Button variant="outline" onClick={onClose} disabled={merge.isPending}>
          {proposed === null ? t('common.cancel') : t('common.done')}
        </Button>
        {proposed === null ? (
          <Button
            disabled={merge.isPending || into === '' || moved === undefined}
            onClick={() =>
              merge.mutate(
                { key: row.key, into },
                {
                  onSuccess: (write) => {
                    if (write.outcome === 'proposed') setProposed(write.proposal.title);
                    else onClose();
                  },
                },
              )
            }
          >
            {t('admin.vocabularies.mergeButton', { count: moved ?? 0 })}
          </Button>
        ) : null}
      </ButtonBar>
    </Modal>
  );
}

// ——— add ——————————————————————————————————————————————————————————

function AddDialog({ list, isLibrary, onClose }: { list: string; isLibrary: boolean; onClose: () => void }) {
  const t = useT();
  const create = useCreateValue(list);
  const [labelEn, setLabelEn] = useState('');
  const [labelSv, setLabelSv] = useState('');
  const [usageNote, setUsageNote] = useState('');
  const [blank, setBlank] = useState(false);
  const [proposed, setProposed] = useState<string | null>(null);
  const candidates = nearDuplicateFrom(create.error);
  const exact = exactDuplicateFrom(create.error)?.[0];

  const submit = (force: boolean) => {
    if (labelEn.trim() === '') {
      setBlank(true);
      return;
    }
    setBlank(false);
    create.mutate(
      { labels: labelsOf(labelEn, labelSv), usageNote: usageNote.trim(), ...(force ? { force: true } : {}) },
      {
        onSuccess: (write) => {
          if (write.outcome === 'proposed') setProposed(write.proposal.title);
          else onClose();
        },
      },
    );
  };

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t('admin.vocabularies.addTitle')}
    >
      {proposed !== null ? (
        <>
          <StatusLine tone="positive">{t('admin.vocabularies.proposed', { title: proposed })}</StatusLine>
          <ButtonBar>
            <Button onClick={onClose}>{t('common.done')}</Button>
          </ButtonBar>
        </>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            submit(false);
          }}
          noValidate
          aria-busy={create.isPending}
        >
          <Field id="add-label" label={t('admin.vocabularies.label')} error={blank ? t('admin.vocabularies.labelRequired') : undefined}>
            <TextInput id="add-label" value={labelEn} autoFocus onChange={(e) => setLabelEn(e.target.value)} />
          </Field>
          <Field id="add-label-sv" label={t('admin.vocabularies.labelSv')} hint={t('admin.vocabularies.labelSvHint')}>
            <TextInput id="add-label-sv" placeholder={t('admin.vocabularies.labelSvPlaceholder')} value={labelSv} onChange={(e) => setLabelSv(e.target.value)} />
          </Field>
          <Field id="add-usage-note" label={t('admin.vocabularies.usageNote')} hint={t('admin.vocabularies.usageNoteHint')}>
            <TextArea id="add-usage-note" placeholder={t('admin.vocabularies.usageNotePlaceholder')} value={usageNote} onChange={(e) => setUsageNote(e.target.value)} />
          </Field>

          <div className="mb-3.5 grid gap-1.5">
            <span className="font-semibold text-meta">{t('admin.vocabularies.preview')}</span>
            <SwatchPair>
              <PillRow pills={[presentVocabularyValue(list, { key: 'preview', kind: null, label: labelEn.trim(), extra: {} })]} />
            </SwatchPair>
          </div>

          {/* AC-VOC3: the server refuses a duplicate and names the value already there. */}
          {exact !== undefined ? (
            <div role="alert" className="mt-2.5 grid gap-1.5" data-duplicate="">
              <p className="text-meta text-negative">{t('picker.alreadyExists', { label: exact.label })}</p>
              <ButtonBar className="mt-0">
                <Button size="small" onClick={onClose}>
                  {t('admin.vocabularies.useExisting', { label: exact.label })}
                </Button>
              </ButtonBar>
            </div>
          ) : candidates !== null && candidates.length > 0 ? (
            <div role="alert" className="mt-2.5 grid gap-1.5" data-near-duplicate="">
              <p className="text-meta text-negative">{t('admin.vocabularies.didYouMean', { label: candidates[0]?.label ?? '' })}</p>
              <ButtonBar className="mt-0">
                <Button variant="outline" size="small" onClick={() => submit(true)} disabled={create.isPending}>
                  {t('admin.vocabularies.addAnyway')}
                </Button>
                <Button
                  size="small"
                  onClick={() => {
                    setLabelEn(candidates[0]?.label ?? '');
                    onClose();
                  }}
                >
                  {t('admin.vocabularies.useExisting', { label: candidates[0]?.label ?? '' })}
                </Button>
              </ButtonBar>
            </div>
          ) : create.isError ? (
            <ProblemAlert error={create.error} />
          ) : null}

          <ButtonBar>
            <Button variant="outline" onClick={onClose} disabled={create.isPending}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {isLibrary ? t('admin.vocabularies.sendForReview') : t('admin.vocabularies.addButton')}
            </Button>
          </ButtonBar>
        </form>
      )}
    </Modal>
  );
}

// ——— the screen ———————————————————————————————————————————————————

export function VocabularyScreen({ list }: { list: string }) {
  const t = useT();
  const lists = useVocabularies();
  const [filter, setFilter] = useState(ACTIVE);
  const values = useVocabularyValues(list, true);
  const reorder = useReorderValues(list);

  const summary = lists.data?.find((entry) => entry.list === list);
  const isLibrary = summary?.tier === 'library';
  // A tenant list is written with vocab.manage, which the route's gate already
  // holds; a library list only by someone who may propose.
  const permissions = usePermissions() ?? [];
  const canWrite = !isLibrary || permissions.includes(PROPOSALS_CREATE);

  const [editing, setEditing] = useState<string | null>(null);
  const [retiring, setRetiring] = useState<VocabularyRow | null>(null);
  const [merging, setMerging] = useState<VocabularyRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [order, setOrder] = useState<string[] | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);

  const rows = useMemo(() => {
    const all = values.data ?? [];
    const active = all.filter((row) => row.active);
    if (order === null) return all;
    const rank = new Map(order.map((key, index) => [key, index]));
    const sorted = [...active].sort((a, b) => (rank.get(a.key) ?? 0) - (rank.get(b.key) ?? 0));
    return [...sorted, ...all.filter((row) => !row.active)];
  }, [values.data, order]);

  const shown = rows.filter((row) => (filter === ACTIVE ? row.active : !row.active));
  const activeKeys = rows.filter((row) => row.active).map((row) => row.key);

  const commitOrder = (keys: string[]) => {
    setOrder(keys);
    reorder.mutate(keys);
  };

  const move = (key: string, to: number) => commitOrder(moveKey(activeKeys, key, to));

  const onDrop = (index: number) => {
    if (dragging === null) return;
    commitOrder(moveKey(activeKeys, dragging, index));
    setDragging(null);
  };

  const title = listLabel(list, t);

  if (values.isPending || lists.isPending) {
    return (
      <>
        <BackLink href="/admin/vocabularies" label={t('admin.vocabularies.title')} />
        <PageHead title={title} />
        <LoadingState rows={3} />
      </>
    );
  }
  if (values.isError) {
    return (
      <>
        <BackLink href="/admin/vocabularies" label={t('admin.vocabularies.title')} />
        <PageHead title={title} />
        <ErrorState title={t('admin.vocabularies.errorTitleOne')} onRetry={() => void values.refetch()} />
      </>
    );
  }

  const activeCount = rows.filter((row) => row.active).length;
  const retiredCount = rows.length - activeCount;
  const kicker =
    retiredCount > 0
      ? t('admin.vocabularies.kickerWithRetired', { tier: isLibrary ? t('admin.vocabularies.tierLibrary') : t('admin.vocabularies.tierTenant'), active: activeCount, retired: retiredCount })
      : t('admin.vocabularies.kickerActive', { tier: isLibrary ? t('admin.vocabularies.tierLibrary') : t('admin.vocabularies.tierTenant'), active: activeCount });

  return (
    <>
      <BackLink href="/admin/vocabularies" label={t('admin.vocabularies.title')} />
      <PageHead
        kicker={kicker}
        title={title}
        actions={canWrite ? <Button onClick={() => setAdding(true)}>{isLibrary ? t('admin.vocabularies.proposeValue') : t('admin.vocabularies.addValue')}</Button> : undefined}
      />

      {isLibrary ? <p className="mb-4 max-w-[70ch] text-muted">{t('admin.vocabularies.libraryLede')}</p> : null}

      <ChipRow className="mb-4">
        <Chip pressed={filter === ACTIVE} onClick={() => setFilter(ACTIVE)}>
          {t('admin.vocabularies.filterActive')}
        </Chip>
        <Chip pressed={filter === RETIRED} onClick={() => setFilter(RETIRED)}>
          {t('admin.vocabularies.filterRetired')}
        </Chip>
        {isLibrary ? null : <span className="text-meta text-muted">{t('admin.vocabularies.reorderHint')}</span>}
      </ChipRow>

      {reorder.isError ? <ProblemAlert error={reorder.error} /> : null}

      {shown.length === 0 ? (
        filter === ACTIVE ? (
          <EmptyState title={t('admin.vocabularies.emptyTitleOne')} body={t('admin.vocabularies.emptyBodyOne')} />
        ) : (
          <EmptyState title={t('admin.vocabularies.noRetiredTitle')} body={t('admin.vocabularies.noRetiredBody')} />
        )
      ) : (
        <Rows data-vocabulary-values={list}>
          {shown.map((row, index) => (
            <ValueRow
              key={row.key}
              list={list}
              row={row}
              index={index}
              count={activeCount}
              isLibrary={isLibrary === true}
              readOnly={!canWrite}
              editing={editing === row.key}
              onEdit={setEditing}
              onRetire={setRetiring}
              onMerge={setMerging}
              onMove={move}
              onDragStart={setDragging}
              onDrop={onDrop}
            />
          ))}
        </Rows>
      )}

      {/* What this tenant has proposed on a library list returns with chunk 4, which adds a read scoped to the proposer's tenant. */}

      {retiring !== null ? <RetireDialog list={list} row={retiring} onClose={() => setRetiring(null)} /> : null}
      {merging !== null ? (
        <MergeDialog list={list} row={merging} targets={rows.filter((row) => row.active && row.key !== merging.key)} onClose={() => setMerging(null)} />
      ) : null}
      {adding ? <AddDialog list={list} isLibrary={isLibrary === true} onClose={() => setAdding(false)} /> : null}
    </>
  );
}
