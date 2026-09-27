'use client';

import { useState, type FormEvent } from 'react';

import { BackLink } from '@/components/admin/AdminGate';
import { PlatformAgentSettingsPanel } from '@/components/console/PlatformAgentSettings';
import { PlatformRunsPanel } from '@/components/console/PlatformRunsPanel';
import { Button, ButtonBar } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Field, TextArea, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { PageHead } from '@/components/ui/PageHead';
import { Panel, Row, Rows } from '@/components/ui/Panel';
import { PillRow } from '@/components/ui/PillRow';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert, StatusLine } from '@/components/ui/States';
import { canRetire, definitionName, presentDefinition, presentVersion } from '@/features/agents/agents-presentation';
import { useAgentDefinition, usePublishAgentVersion, useRetireAgentVersion } from '@/features/agents/hooks';
import type { AgentDefinitionDetail, AgentVersion } from '@/features/agents/types';
import { useFormatContext } from '@/features/identity/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { formatDateTime } from '@/shared/utils/format';
import { problemStatus } from '@/shared/utils/problem';

// One agent definition (design/screens/console-agent-definitions.html, AGT-03,
// ADM-02): its versions, append-only, with publish and retire; and for one of
// bleqq's own agents, how it runs for every bank and what it has run. Publish,
// retire and a settings save each ask for a passkey, which the api client's
// step-up prompt drives off the server's own `step_up_required`. A version is
// published from a folder already in the repository: the screen names the
// folder and never shows a prompt.

function PublishModal({ definition, open, onClose, onPublished }: { definition: AgentDefinitionDetail; open: boolean; onClose: () => void; onPublished: (versionNo: number) => void }) {
  const t = useT();
  const publish = usePublishAgentVersion(definition.key);
  const next = Math.max(0, ...definition.versions.map((v) => v.versionNo)) + 1;
  const [versionNo, setVersionNo] = useState(String(next));
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState<'version' | 'note' | null>(null);
  const chosen = Number(versionNo);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!Number.isInteger(chosen) || chosen < 1) return setProblem('version');
    if (note.trim() === '') return setProblem('note');
    setProblem(null);
    publish.mutate(
      { versionNo: chosen, changeNote: note.trim() },
      {
        onSuccess: (version) => {
          onPublished(version.versionNo);
          setNote('');
          onClose();
        },
      },
    );
  };

  return (
    <Modal open={open} onOpenChange={(isOpen) => (isOpen ? undefined : onClose())} title={t('console.agents.publishTitle')} description={t('console.agents.publishNote')}>
      <form onSubmit={submit} noValidate aria-busy={publish.isPending} data-publish-form="">
        <Field id="agent-version-no" label={t('console.agents.versionLabel')} hint={t('console.agents.versionHint')} error={problem === 'version' ? t('console.agents.versionRequired') : undefined}>
          <TextInput id="agent-version-no" type="number" min={1} step={1} inputMode="numeric" value={versionNo} onChange={(e) => setVersionNo(e.target.value)} />
        </Field>
        <Field id="agent-version-note" label={t('console.agents.changeNote')} hint={t('console.agents.changeNoteHint')} error={problem === 'note' ? t('console.agents.changeNoteRequired') : undefined}>
          <TextArea id="agent-version-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {publish.isError ? <ProblemAlert error={publish.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
        <ButtonBar>
          <Button variant="outline" onClick={onClose} disabled={publish.isPending}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={publish.isPending}>
            {t('console.agents.publishAction', { version: Number.isInteger(chosen) && chosen > 0 ? chosen : next })}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

function VersionRow({ definition, version, onRetired }: { definition: AgentDefinitionDetail; version: AgentVersion; onRetired: (versionNo: number) => void }) {
  const t = useT();
  const ctx = useFormatContext();
  const retire = useRetireAgentVersion(definition.key);
  const [confirming, setConfirming] = useState(false);
  const pills = presentVersion(version, definition.currentVersion, t);

  return (
    <Row data-agent-version={version.versionNo}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{t('agents.versionNo', { version: version.versionNo })}</h3>
        {pills.length > 0 ? <PillRow pills={pills} /> : null}
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-3.5 gap-y-1.5 text-meta md:grid-cols-[150px_1fr]">
        <dt className="text-muted">{t('console.agents.folder')}</dt>
        <dd className="m-0 font-mono break-all">{t('console.agents.folderPath', { key: definition.key, version: version.versionNo })}</dd>
        <dt className="text-muted">{t('console.agents.model')}</dt>
        <dd className="m-0 break-all">{version.model}</dd>
        <dt className="text-muted">{t('console.agents.changeNote')}</dt>
        <dd className="m-0">{version.changeNote}</dd>
        <dt className="text-muted">{t('console.agents.publishedLabel')}</dt>
        <dd className="m-0">
          {version.publishedBy === null ? formatDateTime(version.publishedAt, ctx) : t('console.agents.publishedBy', { date: formatDateTime(version.publishedAt, ctx), name: version.publishedBy.name })}
        </dd>
        {version.retiredAt === null ? null : (
          <>
            <dt className="text-muted">{t('console.agents.retiredLabel')}</dt>
            <dd className="m-0">{formatDateTime(version.retiredAt, ctx)}</dd>
          </>
        )}
      </dl>
      {retire.isError ? <ProblemAlert error={retire.error} codes={{ step_up_required: t('problem.stepUpCancelled') }} /> : null}
      {confirming ? <StatusLine>{t('console.agents.retireBody', { version: version.versionNo })}</StatusLine> : null}
      {canRetire(version, definition.currentVersion) ? (
        <ButtonBar>
          {confirming ? (
            <>
              <Button variant="outline" size="small" onClick={() => setConfirming(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                variant="danger"
                size="small"
                disabled={retire.isPending}
                onClick={() => retire.mutate(version.versionNo, { onSuccess: () => onRetired(version.versionNo), onSettled: () => setConfirming(false) })}
              >
                {t('console.agents.retireAction', { version: version.versionNo })}
              </Button>
            </>
          ) : (
            <Button variant="danger" size="small" onClick={() => setConfirming(true)}>
              {t('console.agents.retire')}
            </Button>
          )}
        </ButtonBar>
      ) : null}
    </Row>
  );
}

function Definition({ definition }: { definition: AgentDefinitionDetail }) {
  const t = useT();
  const name = definitionName(definition.key);
  const [publishing, setPublishing] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const publishButton = <Button onClick={() => setPublishing(true)}>{t('console.agents.publish')}</Button>;

  return (
    <>
      <PageHead title={name} lede={definition.description} actions={publishButton} />
      <div className="mb-4">
        <PillRow pills={presentDefinition(definition, t)} />
      </div>
      {status === null ? null : <StatusLine tone="positive">{status}</StatusLine>}

      <Panel title={t('console.agents.versions')} data-agent-versions="">
        {definition.versions.length === 0 ? (
          <EmptyState title={t('console.agents.noVersionTitle')} body={t('console.agents.noVersionBody')} />
        ) : (
          <>
            <Rows>
              {definition.versions.map((version) => (
                <VersionRow key={version.versionNo} definition={definition} version={version} onRetired={(versionNo) => setStatus(t('console.agents.retiredStatus', { version: versionNo }))} />
              ))}
            </Rows>
            <p className="mt-3 text-meta text-muted">{t('console.agents.versionsNote')}</p>
          </>
        )}
      </Panel>

      {definition.scope === 'platform' ? (
        <>
          <PlatformAgentSettingsPanel agentKey={definition.key} name={name} />
          <PlatformRunsPanel agentKey={definition.key} />
        </>
      ) : (
        <p className="text-meta text-muted" data-tenant-settings-note="">
          {t('console.agents.tenantSettingsNote')}
        </p>
      )}

      {/* Keyed on the versions, so the suggested next number follows a publish. */}
      <PublishModal
        key={definition.versions.length}
        definition={definition}
        open={publishing}
        onClose={() => setPublishing(false)}
        onPublished={(versionNo) => setStatus(t('console.agents.publishedStatus', { name, version: versionNo }))}
      />
    </>
  );
}

export function AgentDefinitionScreen({ agentKey }: { agentKey: string }) {
  const t = useT();
  const definition = useAgentDefinition(agentKey);
  const back = <BackLink href="/console/agents" label={t('console.agents.back')} />;

  if (definition.isPending) {
    return (
      <>
        {back}
        <LoadingState rows={3} />
      </>
    );
  }
  if (definition.isError) {
    const status = problemStatus(definition.error);
    if (status === 404) return <NotFoundScreen body={t('console.agents.notFoundBody')} backHref="/console/agents" backLabel={t('console.agents.back')} />;
    return (
      <>
        {back}
        {/* A refusal is the server's own, rendered as it is; anything else can be tried again. */}
        {status === 403 ? <ProblemAlert error={definition.error} /> : <ErrorState title={t('console.agents.detailErrorTitle')} onRetry={() => void definition.refetch()} />}
      </>
    );
  }
  return (
    <>
      {back}
      <Definition definition={definition.data} />
    </>
  );
}
