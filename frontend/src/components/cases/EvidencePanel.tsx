'use client';

import { useState, type FormEvent } from 'react';

import { Button, ButtonBar } from '@/components/ui/Button';
import { Field, TextInput } from '@/components/ui/Field';
import { Modal } from '@/components/ui/Modal';
import { Meta, Panel } from '@/components/ui/Panel';
import { Pill } from '@/components/ui/Pill';
import { ErrorState, LoadingState, ProblemAlert, StatusLine } from '@/components/ui/States';
import { downloadEvidence } from '@/features/cases/api';
import { isDownloadable, presentScanState } from '@/features/cases/case-presentation';
import { useAddEvidence, useCaseEvidence, useRemoveEvidence } from '@/features/cases/hooks';
import type { CaseEvidence, CasePanelProps, EvidenceKind } from '@/features/cases/types';
import { useFormatContext } from '@/features/identity/hooks';
import { CASES_WORK } from '@/features/watch/hooks';
import { useT } from '@/shared/i18n/LocaleProvider';
import { localeTags, type MessageKey } from '@/shared/i18n';
import { usePermissions } from '@/shared/navigation/require-permission';
import { externalHref } from '@/shared/utils/external-href';
import { formatDate } from '@/shared/utils/format';

import { CASES_CONTRIBUTE, WORKED } from './ActionsPanel';

// The case's evidence (design/screens/tenant-change.html, "Evidence";
// CAS-05). Each row reads its kind, name, a file's size, who attached it and
// when, and a file's scan-state pill; only a checked file downloads. Attach
// is `cases.contribute`, Remove `cases.work`, Download `cases.read`. A file is
// one multipart post with its progress shown; the allowed types and the size
// limit are the server's, quoted from its refusal, never a client copy. The
// download is bytes through the API, saved under the name the server chose:
// no evidence address or file name goes to storage, the address bar or a log.

const CASES_READ = 'cases.read';

const KIND_LABEL = {
  file: 'caseEvidence.kind.file',
  link: 'caseEvidence.kind.link',
  reference: 'caseEvidence.kind.reference',
} as const satisfies Record<EvidenceKind, MessageKey>;

const SCAN_HINT = {
  pending: 'caseEvidence.hint.pending',
  infected: 'caseEvidence.hint.infected',
  error: 'caseEvidence.hint.error',
} as const satisfies Partial<Record<CaseEvidence['scanState'], MessageKey>>;

const ATTACH_REFUSALS = { scanner_unavailable: 'caseEvidence.scannerUnavailable' } as const satisfies Record<string, MessageKey>;
const DOWNLOAD_REFUSALS = { scan_pending: 'caseEvidence.scanPending', scan_failed: 'caseEvidence.scanFailed' } as const satisfies Record<string, MessageKey>;

/** A file's size in the reader's language: "412 kB", "2.1 MB". */
export function formatSize(bytes: number, localeTag: string): string {
  const [value, unit] = bytes >= 1_000_000 ? [bytes / 1_000_000, 'megabyte'] : [Math.max(1, Math.round(bytes / 1000)), 'kilobyte'];
  return new Intl.NumberFormat(localeTag, { style: 'unit', unit, unitDisplay: 'short', maximumFractionDigits: 1 }).format(value);
}

/** Hands the bytes to the browser as a download and lets go of them at once. */
export function saveDownload(content: Blob, fileName: string | null): void {
  const href = URL.createObjectURL(content);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = fileName ?? '';
  anchor.click();
  URL.revokeObjectURL(href);
}

function EvidenceName({ evidence }: { evidence: CaseEvidence }) {
  const t = useT();
  const href = evidence.kind === 'link' && evidence.url !== null ? externalHref(evidence.url) : null;
  if (href === null) return <p className="font-medium break-words">{evidence.name}</p>;
  return (
    <p className="font-medium break-words">
      <a href={href} rel="noopener noreferrer" target="_blank" className="underline">
        {evidence.name}
        <span className="sr-only">{t('caseEvidence.newTab')}</span>
      </a>
    </p>
  );
}

function EvidenceRow({ evidence, canRemove, canDownload, onRemove, onDownload }: {
  evidence: CaseEvidence;
  canRemove: boolean;
  canDownload: boolean;
  onRemove: () => void;
  onDownload: () => void;
}) {
  const t = useT();
  const ctx = useFormatContext();
  const scan = evidence.kind === 'file' ? presentScanState(evidence.scanState, t) : null;
  const hint = evidence.kind === 'file' && evidence.scanState !== 'clean' ? SCAN_HINT[evidence.scanState] : null;
  return (
    <div className="flex items-start gap-2.5 border-b border-line py-2.5 last:border-b-0" data-evidence={evidence.id} data-scan-state={evidence.kind === 'file' ? evidence.scanState : undefined}>
      <div className="min-w-0 flex-1">
        <EvidenceName evidence={evidence} />
        <Meta className="mt-1">
          <span>{t(KIND_LABEL[evidence.kind])}</span>
          {evidence.sizeBytes === null ? null : <span className="tabular-nums">{formatSize(evidence.sizeBytes, localeTags[ctx.locale])}</span>}
          {evidence.kind === 'link' && evidence.url !== null ? <span className="font-mono break-all">{evidence.url}</span> : null}
          <span>{t('caseEvidence.addedBy', { name: evidence.uploadedBy.name, date: formatDate(evidence.uploadedAt, ctx) })}</span>
          {scan === null ? null : <Pill tone={scan.tone}>{scan.label}</Pill>}
        </Meta>
        {hint === null ? null : <p className="mt-1 text-meta text-muted">{t(hint)}</p>}
      </div>
      <div className="flex gap-2">
        {canRemove ? (
          <Button variant="ghost" size="small" onClick={onRemove}>
            {t('caseEvidence.remove')}
          </Button>
        ) : null}
        {canDownload && isDownloadable(evidence) ? (
          <Button size="small" onClick={onDownload}>
            {t('caseEvidence.download')}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

const KINDS: readonly { kind: EvidenceKind; label: MessageKey; hint: MessageKey }[] = [
  { kind: 'file', label: 'caseEvidence.kindFile', hint: 'caseEvidence.kindFileHint' },
  { kind: 'link', label: 'caseEvidence.kindLink', hint: 'caseEvidence.kindLinkHint' },
  { kind: 'reference', label: 'caseEvidence.kindReference', hint: 'caseEvidence.kindReferenceHint' },
];

function AttachDialog({ changeId, open, onClose, onAttached }: { changeId: string; open: boolean; onClose: () => void; onAttached: (kind: EvidenceKind) => void }) {
  const t = useT();
  const [kind, setKind] = useState<EvidenceKind>('file');
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [sent, setSent] = useState(0);
  const attach = useAddEvidence(changeId, setSent);

  function close() {
    if (attach.isPending) return;
    attach.reset();
    setFile(null);
    setName('');
    setUrl('');
    setSent(0);
    onClose();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setSent(0);
    const input =
      kind === 'file' ? { kind, name: file?.name ?? '', ...(file === null ? {} : { file }) } : kind === 'link' ? { kind, name, url } : { kind, name };
    attach.mutate(input, {
      onSuccess: () => {
        onAttached(kind);
        close();
      },
    });
  }

  return (
    <Modal open={open} onOpenChange={(next) => (next ? undefined : close())} title={t('caseEvidence.attach')}>
      <form onSubmit={submit} aria-busy={attach.isPending || undefined} data-attach-evidence="">
        <fieldset className="mb-3 grid border-0 p-0" disabled={attach.isPending}>
          <legend className="mb-1 font-medium">{t('caseEvidence.kindLegend')}</legend>
          {KINDS.map((option) => (
            <label key={option.kind} className="flex items-start gap-2.5 border-b border-line py-2 last:border-b-0">
              <input type="radio" name="evidence-kind" className="mt-0.5 size-4 accent-button" checked={kind === option.kind} onChange={() => setKind(option.kind)} />
              <span>
                {t(option.label)}
                <small className="block text-meta text-muted">{t(option.hint)}</small>
              </span>
            </label>
          ))}
        </fieldset>
        {kind === 'file' ? (
          <Field id="evidence-file" label={t('caseEvidence.file')}>
            <input id="evidence-file" type="file" disabled={attach.isPending} onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </Field>
        ) : (
          <Field id="evidence-name" label={t(kind === 'link' ? 'caseEvidence.name' : 'caseEvidence.document')} hint={kind === 'reference' ? t('caseEvidence.documentHint') : undefined}>
            <TextInput id="evidence-name" value={name} disabled={attach.isPending} onChange={(event) => setName(event.target.value)} />
          </Field>
        )}
        {kind === 'link' ? (
          <Field id="evidence-url" label={t('caseEvidence.url')}>
            <TextInput id="evidence-url" type="url" inputMode="url" value={url} disabled={attach.isPending} onChange={(event) => setUrl(event.target.value)} />
          </Field>
        ) : null}
        {attach.isPending && kind === 'file' ? (
          <div role="status" data-upload-progress="">
            <p className="text-meta text-muted tabular-nums">{t('caseEvidence.uploading', { percent: Math.round(sent * 100) })}</p>
            <progress className="mt-1 w-full" max={1} value={sent} />
          </div>
        ) : null}
        <ProblemAlert error={attach.error} codes={{ scanner_unavailable: t(ATTACH_REFUSALS.scanner_unavailable) }} />
        <ButtonBar>
          <Button variant="outline" disabled={attach.isPending} onClick={close}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" disabled={attach.isPending}>
            {t('caseEvidence.attach')}
          </Button>
        </ButtonBar>
      </form>
    </Modal>
  );
}

export function EvidencePanel({ change, workflow }: CasePanelProps) {
  const t = useT();
  const permissions = usePermissions() ?? [];
  const evidence = useCaseEvidence(change.id);
  const remove = useRemoveEvidence(change.id);
  const [attaching, setAttaching] = useState(false);
  const [attached, setAttached] = useState<EvidenceKind | null>(null);
  const [removing, setRemoving] = useState<CaseEvidence | null>(null);
  const [downloadError, setDownloadError] = useState<unknown>(null);

  const worked = WORKED.includes(workflow.category);
  const canAttach = worked && permissions.includes(CASES_CONTRIBUTE);
  const canRemove = worked && permissions.includes(CASES_WORK);
  const canDownload = permissions.includes(CASES_READ);

  async function download(item: CaseEvidence) {
    setDownloadError(null);
    try {
      const { content, fileName } = await downloadEvidence(item.id);
      saveDownload(content, fileName);
    } catch (error) {
      setDownloadError(error);
    }
  }

  function confirmRemove() {
    if (removing === null) return;
    remove.mutate(removing.id, { onSettled: () => setRemoving(null) });
  }

  let body;
  if (evidence.isPending) body = <LoadingState />;
  else if (evidence.isError) body = <ErrorState title={t('caseEvidence.loadError')} onRetry={() => void evidence.refetch()} />;
  else if (evidence.data.items.length === 0) {
    body = (
      <div className="py-4 text-center text-muted" data-evidence-empty="">
        <h3 className="text-fg">{t('caseEvidence.empty.title')}</h3>
        <p className="mt-1">{t('caseEvidence.empty.body')}</p>
      </div>
    );
  } else {
    body = (
      <div>
        {evidence.data.items.map((item) => (
          <EvidenceRow
            key={item.id}
            evidence={item}
            canRemove={canRemove}
            canDownload={canDownload}
            onRemove={() => setRemoving(item)}
            onDownload={() => void download(item)}
          />
        ))}
      </div>
    );
  }

  return (
    <Panel title={t('caseEvidence.heading')} data-case-panel="evidence">
      {workflow.category === 'signoff' ? <p className="mb-1 text-meta text-muted" data-evidence-read-only="">{t('caseEvidence.readOnly')}</p> : null}
      {body}
      <ProblemAlert
        error={downloadError ?? remove.error}
        codes={{ scan_pending: t(DOWNLOAD_REFUSALS.scan_pending), scan_failed: t(DOWNLOAD_REFUSALS.scan_failed) }}
      />
      {attached === null ? null : (
        <StatusLine tone="positive">{t(attached === 'file' ? 'caseEvidence.attachedFile' : 'caseEvidence.attached')}</StatusLine>
      )}
      {canAttach ? (
        <ButtonBar>
          <Button
            onClick={() => {
              setAttached(null);
              setAttaching(true);
            }}
          >
            {t('caseEvidence.attach')}
          </Button>
        </ButtonBar>
      ) : null}
      {canAttach ? <AttachDialog changeId={change.id} open={attaching} onClose={() => setAttaching(false)} onAttached={setAttached} /> : null}
      <Modal
        open={removing !== null}
        onOpenChange={(open) => (open ? undefined : setRemoving(null))}
        title={t('caseEvidence.removeTitle', { name: removing?.name ?? '' })}
        description={t('caseEvidence.removeBody')}
      >
        <ButtonBar>
          <Button variant="outline" onClick={() => setRemoving(null)}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={remove.isPending} onClick={confirmRemove}>
            {t('caseEvidence.remove')}
          </Button>
        </ButtonBar>
      </Modal>
    </Panel>
  );
}
