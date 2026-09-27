'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Panel } from '@/components/ui/Panel';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { useCaseFile } from '@/features/cases/hooks';
import type { CasePanelProps } from '@/features/cases/types';
import type { components } from '@/types/api.generated';
import { useT } from '@/shared/i18n/LocaleProvider';
import { usePermissions } from '@/shared/navigation/require-permission';
import { api, STEP_UP_REQUIRED_CODE } from '@/shared/utils/api-client';

// Show case file and Export on the change page (CAS-07; design/screens/
// tenant-change.html, "Show case file"), in every status. The text is the
// server's own, in the reader's language with every date on the bank's clock
// (apps/cases/case_file.py); the panel only splits it at its underlined
// headings and sets a SHA-256 in monospace. Export turns the same text into a
// file through the exports job: `POST /exports` with a passkey (the api client
// opens the shared prompt on 403 `step_up_required`), `GET /exports/{id}`
// until it is built, and the download, permission-checked again by the server.

const READ = 'cases.read';
const EXPORT = 'exports.create';

type ExportJob = components['schemas']['ExportJobOut'];
type ExportInput = components['schemas']['ExportInput'];

const EXPORTS = '/api/v1/exports';
/** How often a job still being built is read again. */
const EXPORT_POLL_MS = 2000;

async function createExport(body: ExportInput): Promise<ExportJob> {
  return (await api.post<ExportJob>(EXPORTS, body)).data;
}

async function getExport(exportId: string): Promise<ExportJob> {
  return (await api.get<ExportJob>(`${EXPORTS}/${encodeURIComponent(exportId)}`)).data;
}

/** Streams the built file and hands it to the browser to save, under the name the server gives it. */
async function downloadExport(job: ExportJob): Promise<void> {
  const blob = (
    await api.get<Blob>(`${EXPORTS}/${encodeURIComponent(job.id)}/download`, {
      responseType: 'blob',
    })
  ).data;
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = `${job.kind}-${(job.completedAt ?? job.createdAt).slice(0, 10)}.${job.format}`;
  link.click();
  URL.revokeObjectURL(href);
}

export interface CaseFileSection {
  heading: string | null;
  lines: string[];
}

const UNDERLINE = /^=+$/;
const SHA256 = /([0-9a-f]{64})/;

/**
 * The case file's text in its sections: a line underlined with as many `=`
 * as it has characters is a heading, and every other non-empty line is kept
 * as written. The lines before the first heading are the change itself.
 */
export function caseFileSections(text: string): CaseFileSection[] {
  const lines = text.split('\n');
  let current: CaseFileSection = { heading: null, lines: [] };
  const sections = [current];
  lines.forEach((line, index) => {
    const next = lines[index + 1] ?? '';
    const previous = lines[index - 1] ?? '';
    if (UNDERLINE.test(line) && previous === current.heading) return;
    if (line !== '' && UNDERLINE.test(next) && next.length === line.length) {
      current = { heading: line, lines: [] };
      sections.push(current);
    } else if (line.trim() !== '') {
      current.lines.push(line);
    }
  });
  return sections.filter((section) => section.heading !== null || section.lines.length > 0);
}

function CaseFileLine({ line }: { line: string }) {
  return (
    <p className="break-words whitespace-pre-wrap">
      {line.split(SHA256).map((part, index) =>
        index % 2 === 1 ? (
          <code key={index} className="font-mono break-all">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </p>
  );
}

function CaseFileText({ text }: { text: string }) {
  const t = useT();
  return (
    <div tabIndex={0} aria-label={t('caseFile.textLabel')} className="grid gap-3 rounded-control border border-line bg-subtle p-3 text-meta" data-case-file-text="">
      {caseFileSections(text).map((section, index) => (
        <section key={index}>
          {section.heading === null ? null : <h3 className="microlabel mb-1">{section.heading}</h3>}
          {section.lines.map((line, row) => (
            <CaseFileLine key={row} line={line} />
          ))}
        </section>
      ))}
    </div>
  );
}

function ExportJobState({ created }: { created: ExportJob }) {
  const t = useT();
  const job = useQuery({
    queryKey: ['exports', created.id],
    queryFn: () => getExport(created.id),
    refetchInterval: (query) => (query.state.data?.status === 'succeeded' || query.state.data?.status === 'failed' ? false : EXPORT_POLL_MS),
  });
  const download = useMutation({ mutationFn: downloadExport });
  const current = job.data ?? created;

  return (
    <>
      {current.status === 'succeeded' ? (
        <StatusLine tone="positive">
          {t('caseFile.exportReady')}{' '}
          <Button variant="outline" size="small" disabled={download.isPending} onClick={() => download.mutate(current)}>
            {t('caseFile.download')}
          </Button>
        </StatusLine>
      ) : current.status === 'failed' ? (
        <p role="alert" className="mt-2.5 text-meta text-negative">
          {t('caseFile.exportFailed')}
        </p>
      ) : (
        <StatusLine>{t('caseFile.exportPreparing')}</StatusLine>
      )}
      {job.isError ? <ProblemAlert error={job.error} /> : null}
      {download.isError ? <ProblemAlert error={download.error} codes={{ export_expired: t('caseFile.exportExpired') }} /> : null}
    </>
  );
}

function CaseFileModal({ changeId, caseId, canExport, onOpenChange }: { changeId: string; caseId: string; canExport: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const file = useCaseFile(changeId);
  const create = useMutation({ mutationFn: createExport });
  return (
    <Modal open onOpenChange={onOpenChange} title={t('caseFile.heading')}>
      {file.isPending ? (
        <LoadingState rows={2} />
      ) : file.isError ? (
        <ErrorState title={t('caseFile.errorTitle')} onRetry={() => void file.refetch()} />
      ) : (
        <CaseFileText text={file.data} />
      )}
      {create.data === undefined ? null : <ExportJobState key={create.data.id} created={create.data} />}
      {create.isError ? <ProblemAlert error={create.error} codes={{ [STEP_UP_REQUIRED_CODE]: t('caseFile.stepUpCancelled') }} /> : null}
      <ButtonBar>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          {t('caseFile.close')}
        </Button>
        {canExport ? (
          <Button
            disabled={create.isPending}
            onClick={() =>
              create.mutate({
                kind: 'case_file',
                subjectId: caseId,
                format: 'txt',
              })
            }
          >
            {t('caseFile.export')}
          </Button>
        ) : null}
      </ButtonBar>
    </Modal>
  );
}

export function CaseFilePanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const [open, setOpen] = useState(false);
  if (!permissions.includes(READ)) return null;
  return (
    <Panel title={t('caseFile.heading')} data-case-file-panel="">
      <p className="text-meta text-muted">{t('caseFile.intro')}</p>
      <ButtonBar>
        <Button variant="outline" onClick={() => setOpen(true)}>
          {t('caseFile.show')}
        </Button>
      </ButtonBar>
      {open ? <CaseFileModal changeId={change.id} caseId={workflow.id} canExport={permissions.includes(EXPORT)} onOpenChange={setOpen} /> : null}
    </Panel>
  );
}
