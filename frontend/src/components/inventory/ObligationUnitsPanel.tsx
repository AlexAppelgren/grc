'use client';

import { useState, type FormEvent } from 'react';

import { PasteUnitsDialog } from '@/components/inventory/PasteUnitsDialog';
import { SoaView } from '@/components/inventory/SoaView';
import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, Select, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { TabPanel, Tabs } from '@/components/ui/Tabs';
import { useFormatContext } from '@/features/identity/hooks';
import { isStaleWrite, useCreateUnit, useRegisterEntry, useReloadRegister, useRemoveUnit, useUnits, useUpdateUnit } from '@/features/register/hooks';
import { presentApplicability, presentCompliance } from '@/features/register/register-presentation';
import type { RegisterUnit } from '@/features/register/types';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { formatDate } from '@/shared/utils/format';

// "Units": the Statement of Applicability units under a standard's conformance
// obligation (design/screens/tenant-obligation-units.html; REG-08, REG-01).
// ObligationScreen mounts it only on a standard's conformance obligation. The
// units are listed per legal entity, and the picker offers only the entities
// whose conformance row applies; the others are named in its hint. Add, rename,
// remove and paste need register.edit; rename and remove send If-Match and give
// way to a fixed line once the unit has history, so a decision can never be
// moved to another control. The form asks for the bank's own words and has no
// field for the standard's text. A status is shown only beside "Applies": none
// is asked of a unit that does not apply or is not decided. The Statement of
// Applicability tab shows the same entity's units read-only (SoaView).

const REGISTER_EDIT = 'register.edit';
const APPLICABILITY_APPROVE = 'applicability.approve';
const PAGE_SIZE = 100;

interface Entity {
  id: string;
  name: string;
}

export function ObligationUnitsPanel({ obligationId }: { obligationId: string }) {
  const t = useT();
  const entry = useRegisterEntry(obligationId);
  const [chosen, setChosen] = useState<string | null>(null);

  if (entry.isPending) {
    return (
      <Panel title={t('obligationUnits.heading')}>
        <LoadingState />
      </Panel>
    );
  }
  if (entry.isError) {
    return (
      <Panel title={t('obligationUnits.heading')}>
        <ErrorState title={t('obligationUnits.loadError')} onRetry={() => void entry.refetch()} />
      </Panel>
    );
  }
  const applying = entry.data.entities.filter((row) => row.applicability === 'applies');
  const others = entry.data.entities.filter((row) => row.applicability !== 'applies').map((row) => row.orgUnitName);
  const current = applying.find((row) => row.orgUnitId === chosen) ?? applying[0];

  return (
    <Panel title={t('obligationUnits.heading')} data-units-panel="">
      <p className="mb-3 text-muted">{t('obligationUnits.lede')}</p>
      {current === undefined ? (
        <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-units-no-entity="">
          <h3 className="text-fg">{t('obligationUnits.noEntityTitle')}</h3>
          <p className="mx-auto mt-2 max-w-[60ch]">{t('obligationUnits.noEntityBody')}</p>
        </div>
      ) : (
        <>
          <Field
            id="units-entity"
            label={t('obligationUnits.entity')}
            hint={others.length > 0 ? t('obligationUnits.entityHintOthers', { entities: others.join(', ') }) : t('obligationUnits.entityHint')}
          >
            <Select id="units-entity" aria-describedby="units-entity-hint" value={current.orgUnitId} onChange={(event) => setChosen(event.target.value)}>
              {applying.map((row) => (
                <option key={row.orgUnitId} value={row.orgUnitId}>
                  {row.orgUnitName}
                </option>
              ))}
            </Select>
          </Field>
          <EntityUnits key={current.orgUnitId} obligationId={obligationId} entity={{ id: current.orgUnitId, name: current.orgUnitName }} />
        </>
      )}
    </Panel>
  );
}

function EntityUnits({ obligationId, entity }: { obligationId: string; entity: Entity }) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const canEdit = permissions.includes(REGISTER_EDIT);
  const [offset, setOffset] = useState(0);
  const units = useUnits(obligationId, entity.id, { limit: PAGE_SIZE, offset });
  const [adding, setAdding] = useState(false);
  const [pasting, setPasting] = useState(false);
  const [renaming, setRenaming] = useState<RegisterUnit | null>(null);
  const [removing, setRemoving] = useState<RegisterUnit | null>(null);
  const [created, setCreated] = useState<number | null>(null);
  const [tab, setTab] = useState('units-list');
  const tabs = [
    { id: 'units-list', label: t('obligationUnits.tabUnits') },
    { id: 'units-soa', label: t('obligationUnits.tabStatement') },
  ];

  const actions = canEdit ? (
    <ButtonBar className="mt-0 mb-3">
      <Button variant="outline" size="small" onClick={() => setPasting(true)}>
        {t('obligationUnits.paste')}
      </Button>
      <Button size="small" onClick={() => setAdding(true)}>
        {t('obligationUnits.add')}
      </Button>
    </ButtonBar>
  ) : null;

  return (
    <div data-units-entity={entity.id}>
      <Tabs tabs={tabs} current={tab} onSelect={setTab} />
      {tab === 'units-soa' ? (
        <TabPanel id="units-soa">
          <SoaView obligationId={obligationId} entity={entity} />
        </TabPanel>
      ) : (
        <TabPanel id="units-list">
          {actions}
          {created !== null ? <StatusLine tone="positive">{t('obligationUnits.created', { count: created })}</StatusLine> : null}
          {units.isPending ? (
            <LoadingState />
          ) : units.isError ? (
            <ErrorState title={t('obligationUnits.loadError')} onRetry={() => void units.refetch()} />
          ) : units.data.total === 0 ? (
            <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-units-empty="">
              <h3 className="text-fg">{t('obligationUnits.emptyTitle', { entity: entity.name })}</h3>
              <p className="mx-auto mt-2 max-w-[60ch]">{t('obligationUnits.emptyBody')}</p>
            </div>
          ) : (
            <>
              <p className="mb-2 text-meta text-muted">{t('obligationUnits.count', { count: units.data.total })}</p>
              <Rows>
                {units.data.items.map((unit) => (
                  <UnitRow key={unit.id} unit={unit} canEdit={canEdit} onRename={() => setRenaming(unit)} onRemove={() => setRemoving(unit)} />
                ))}
              </Rows>
              {units.data.total > PAGE_SIZE ? (
                <ButtonBar>
                  <Button variant="outline" size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                    {t('obligationUnits.previous')}
                  </Button>
                  <Button variant="outline" size="small" disabled={offset + PAGE_SIZE >= units.data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                    {t('obligationUnits.next')}
                  </Button>
                </ButtonBar>
              ) : null}
            </>
          )}
        </TabPanel>
      )}

      {canEdit ? (
        <>
          <UnitFormDialog obligationId={obligationId} entity={entity} open={adding} unit={null} onClose={() => setAdding(false)} />
          <UnitFormDialog obligationId={obligationId} entity={entity} open={renaming !== null} unit={renaming} onClose={() => setRenaming(null)} />
          <RemoveUnitDialog unit={removing} onClose={() => setRemoving(null)} />
          <PasteUnitsDialog
            obligationId={obligationId}
            entity={entity}
            canDecide={permissions.includes(APPLICABILITY_APPROVE)}
            open={pasting}
            onOpenChange={setPasting}
            onCreated={setCreated}
          />
        </>
      ) : null}
    </div>
  );
}

function UnitRow({ unit, canEdit, onRename, onRemove }: { unit: RegisterUnit; canEdit: boolean; onRename: () => void; onRemove: () => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const decidedBy = unit.applicabilityDecidedBy;
  return (
    <Row data-unit-id={unit.id}>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-mono text-meta">{unit.reference}</span>
        <h3 className="text-body font-medium">{unit.title}</h3>
      </div>
      <div className="mt-1.5">
        <PillRow pills={unit.applicability === 'applies' ? [presentApplicability(unit.applicability, t), presentCompliance(unit.complianceStatus)] : [presentApplicability(unit.applicability, t)]} />
      </div>
      {unit.applicabilityReason !== null && unit.applicabilityReason !== undefined ? <p className="mt-1.5">{unit.applicabilityReason}</p> : null}
      <Meta className="mt-1.5">
        {decidedBy !== null && decidedBy !== undefined && unit.applicabilityDecidedAt !== null && unit.applicabilityDecidedAt !== undefined ? (
          <>
            <span>{t('obligationUnits.setBy', { person: decidedBy.name })}</span>
            <span>{formatDate(unit.applicabilityDecidedAt, ctx)}</span>
          </>
        ) : (
          <span>{t('obligationUnits.noDecision')}</span>
        )}
      </Meta>
      {unit.hasHistory ? (
        <p className="mt-1.5 text-meta text-muted" data-unit-locked="">
          {t('obligationUnits.locked')}
        </p>
      ) : canEdit ? (
        <ButtonBar className="mt-2">
          <Button variant="ghost" size="small" onClick={onRemove}>
            {t('obligationUnits.remove')}
          </Button>
          <Button variant="outline" size="small" onClick={onRename}>
            {t('obligationUnits.rename')}
          </Button>
        </ButtonBar>
      ) : null}
    </Row>
  );
}

/** Stale-write notice with the reload that fetches the version someone else saved. */
function StaleWrite({ onReload }: { onReload: () => void }) {
  const t = useT();
  return (
    <div className="mt-2.5">
      <p role="alert" className="text-meta text-negative" data-problem-code="stale_write">
        {t('obligationUnits.problemStale')}
      </p>
      <Button variant="outline" size="small" className="mt-2" onClick={onReload}>
        {t('obligationUnits.reload')}
      </Button>
    </div>
  );
}

/** Add a unit (`unit` null) or rename one that has no history yet, prefilled. */
function UnitFormDialog({ obligationId, entity, open, unit, onClose }: { obligationId: string; entity: Entity; open: boolean; unit: RegisterUnit | null; onClose: () => void }) {
  const t = useT();
  const create = useCreateUnit(obligationId);
  const update = useUpdateUnit();
  const reload = useReloadRegister();
  const [reference, setReference] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const write = unit === null ? create : update;
  const shownReference = reference ?? unit?.reference ?? '';
  const shownTitle = title ?? unit?.title ?? '';

  const close = () => {
    setReference(null);
    setTitle(null);
    create.reset();
    update.reset();
    onClose();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = { reference: shownReference.trim(), title: shownTitle.trim() };
    const done = { onSuccess: close };
    if (unit === null) create.mutate({ orgUnitId: entity.id, ...body }, done);
    else update.mutate({ unitId: unit.id, body, version: unit.version }, done);
  };

  const codes = {
    duplicate_key: t('obligationUnits.problemDuplicate', { entity: entity.name }),
    scope_not_applicable: t('obligationUnits.problemScope', { entity: entity.name }),
    units_only_under_standards: t('obligationUnits.problemStandard'),
    unit_has_history: t('obligationUnits.problemHistory'),
  };

  return (
    <Modal
      open={open}
      onOpenChange={(next) => (next ? undefined : close())}
      title={unit === null ? t('obligationUnits.addTitle', { entity: entity.name }) : t('obligationUnits.renameTitle', { reference: unit.reference })}
    >
      <form onSubmit={submit} noValidate aria-busy={write.isPending}>
        <Field id="unit-reference" label={t('obligationUnits.reference')}>
          <TextInput id="unit-reference" className="font-mono" value={shownReference} onChange={(event) => setReference(event.target.value)} />
        </Field>
        <Field id="unit-title" label={t('obligationUnits.title')} hint={t('obligationUnits.titleHint')}>
          <TextInput id="unit-title" aria-describedby="unit-title-hint" value={shownTitle} onChange={(event) => setTitle(event.target.value)} />
        </Field>
        {write.isError ? (
          isStaleWrite(write.error) ? (
            <StaleWrite
              onReload={() => {
                void reload();
                close();
              }}
            />
          ) : (
            <ProblemAlert error={write.error} codes={codes} />
          )
        ) : null}
        <ButtonBar>
          <Button variant="outline" onClick={close}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={shownReference.trim() === '' || shownTitle.trim() === '' || write.isPending}>
            {unit === null ? t('obligationUnits.addSubmit') : t('common.save')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function RemoveUnitDialog({ unit, onClose }: { unit: RegisterUnit | null; onClose: () => void }) {
  const t = useT();
  const remove = useRemoveUnit();
  const reload = useReloadRegister();
  const close = () => {
    remove.reset();
    onClose();
  };
  return (
    <Modal
      open={unit !== null}
      onOpenChange={(next) => (next ? undefined : close())}
      title={t('obligationUnits.removeTitle', { reference: unit?.reference ?? '' })}
      description={t('obligationUnits.removeBody', { title: unit?.title ?? '' })}
    >
      {remove.isError ? (
        isStaleWrite(remove.error) ? (
          <StaleWrite
            onReload={() => {
              void reload();
              close();
            }}
          />
        ) : (
          <ProblemAlert error={remove.error} codes={{ unit_has_history: t('obligationUnits.problemHistory') }} />
        )
      ) : null}
      <ButtonBar>
        <Button variant="outline" onClick={close}>
          {t('common.cancel')}
        </Button>
        <Button
          disabled={remove.isPending}
          onClick={() => {
            if (unit !== null) remove.mutate({ unitId: unit.id, version: unit.version }, { onSuccess: close });
          }}
        >
          {t('obligationUnits.remove')}
        </Button>
      </ButtonBar>
    </Modal>
  );
}
