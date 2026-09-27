import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fileNameOf } from '@/features/cases/api';
import { presentScanState } from '@/features/cases/case-presentation';
import type { CaseEvidence, CaseWorkflow } from '@/features/cases/types';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { api, tokenStore } from '@/shared/utils/api-client';

import { EvidencePanel, formatSize, saveDownload } from './EvidencePanel';

// The Evidence panel (design/screens/tenant-change.html, "Evidence"; CAS-05):
// the scan-state pill by kind, a multipart upload with its progress, a link
// and a reference, the server's own refusals, a download only for a checked
// file and only through the API, no address or file name kept anywhere, and
// remove with its confirm.

const t = createT('en');
const SESSION = { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, enrolmentPending: false, permissions: [] };
const WORKER = ['cases.read', 'cases.work', 'cases.contribute'];
const CONTRIBUTOR = ['cases.read', 'cases.contribute'];
const READER = ['cases.read'];

const by = { id: 'u-1', name: 'Johan Berg' };
function file(id: string, name: string, scanState: CaseEvidence['scanState']): CaseEvidence {
  return { id, kind: 'file', name, url: null, sizeBytes: 412_000, mimeType: 'application/pdf', contentHash: `sha256:${'a'.repeat(64)}`, scanState, uploadedBy: by, uploadedAt: '2026-09-18T10:00:00Z' };
}
const CLEAN = file('e-1', 'research-assessment-criteria-v2.pdf', 'clean');
const PENDING = file('e-2', 'provider-assessment-2026.xlsx', 'pending');
const INFECTED = file('e-3', 'minutes-scan.pdf', 'infected');
const FAILED = file('e-4', 'criteria-draft.docx', 'error');
const LINK: CaseEvidence = { ...file('e-5', 'Investment committee minutes', 'clean'), kind: 'link', url: 'https://intranet.bank.example/ic/2026-09', sizeBytes: null, mimeType: null, contentHash: null };
const UNSAFE_LINK: CaseEvidence = { ...LINK, id: 'e-6', name: 'Not a web address', url: 'javascript:alert(1)' };
const REFERENCE: CaseEvidence = { ...LINK, id: 'e-7', kind: 'reference', name: 'Inducements policy, section 4', url: null };
const ALL = [CLEAN, PENDING, INFECTED, FAILED, LINK, UNSAFE_LINK, REFERENCE];

function serve(route: (sent: Sent) => Answer | undefined, items: CaseEvidence[] = ALL): Sent[] {
  return installAdapter((sent) => {
    const scripted = route(sent);
    if (scripted !== undefined) return scripted;
    if (sent.method === 'get' && sent.path === '/api/v1/changes/c-1/evidence') return { status: 200, data: { items, total: items.length } };
    return { status: 200, data: SESSION };
  });
}

function renderPanel(permissions: string[], category: CaseWorkflow['category'] = 'implementing'): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <EvidencePanel change={{ id: 'c-1' } as never} workflow={{ category, version: 6 } as CaseWorkflow} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

const row = (id: string) => within(document.querySelector(`[data-evidence="${id}"]`) as HTMLElement);
const writes = (sent: Sent[]) => sent.filter((request) => request.method !== 'get');

beforeEach(() => {
  cleanup();
  resetApiForTests();
  tokenStore.set('tok');
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('the scan state', () => {
  it('has one tone per state, by kind', () => {
    expect((['pending', 'clean', 'error', 'infected'] as const).map((state) => [presentScanState(state, t).label, presentScanState(state, t).tone])).toEqual([
      ['Being checked', 'notice'],
      ['Checked', 'positive'],
      ['Could not be checked', 'warning'],
      ['Refused, malware found', 'negative'],
    ]);
  });

  it('shows a file’s pill and why it cannot be opened; a link and a reference have none', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    expect(row('e-1').getByText('Checked').closest('[data-pill]')).toHaveAttribute('data-pill', 'positive');
    expect(row('e-1').getByText('412 kB')).toHaveClass('tabular-nums');
    expect(row('e-2').getByText('Being checked').closest('[data-pill]')).toHaveAttribute('data-pill', 'notice');
    expect(row('e-2').getByText('It can be opened once it has been checked for malware.')).toBeInTheDocument();
    expect(row('e-3').getByText('Refused, malware found').closest('[data-pill]')).toHaveAttribute('data-pill', 'negative');
    expect(row('e-3').getByText('The file was deleted. Its name and fingerprint stay on the case.')).toBeInTheDocument();
    expect(row('e-4').getByText('Could not be checked').closest('[data-pill]')).toHaveAttribute('data-pill', 'warning');
    expect(row('e-4').getByText('Nobody can open it. Remove it and attach the file again.')).toBeInTheDocument();
    for (const id of ['e-5', 'e-7']) expect(row(id).queryByText('Checked')).toBeNull();
  });
});

describe('download', () => {
  it('is offered for a checked file only', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    expect(row('e-1').getByRole('button', { name: 'Download' })).toBeInTheDocument();
    for (const id of ['e-2', 'e-3', 'e-4', 'e-5', 'e-7']) expect(row(id).queryByRole('button', { name: 'Download' })).toBeNull();
  });

  it('fetches the bytes through the API and saves them under the server’s name, keeping nothing', async () => {
    const saved: { href: string; download: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      saved.push({ href: this.href, download: this.download });
    });
    const created = vi.fn(() => 'blob:local/1');
    const revoked = vi.fn();
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked });
    const info = vi.spyOn(console, 'info');
    const sent = serve(() => undefined);
    api.defaults.adapter = async (config) => {
      if (config.url?.endsWith('/download')) {
        const response: AxiosResponse = {
          data: new Blob(['%PDF-1.7']),
          status: 200,
          statusText: 'OK',
          headers: { 'content-disposition': 'attachment; filename="research-assessment-criteria-v2.pdf"' },
          config: config as InternalAxiosRequestConfig,
        };
        return response;
      }
      const answer = { status: 200, data: config.url?.endsWith('/evidence') ? { items: ALL, total: ALL.length } : SESSION };
      return { ...answer, statusText: 'OK', headers: {}, config: config as InternalAxiosRequestConfig };
    };
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    const addressBefore = window.location.href;
    fireEvent.click(row('e-1').getByRole('button', { name: 'Download' }));

    await waitFor(() => expect(saved).toEqual([{ href: 'blob:local/1', download: 'research-assessment-criteria-v2.pdf' }]));
    expect(revoked).toHaveBeenCalledWith('blob:local/1');
    expect(window.location.href).toBe(addressBefore);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(info).not.toHaveBeenCalled();
    expect(writes(sent)).toEqual([]);
  });

  it('a refusal from a stale list is read back from its bytes and said in words', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    api.defaults.adapter = async (config) => {
      const response: AxiosResponse = {
        data: new Blob([JSON.stringify({ code: 'scan_pending', detail: 'Pending.' })], { type: 'application/problem+json' }),
        status: 409,
        statusText: '409',
        headers: {},
        config: config as InternalAxiosRequestConfig,
      };
      throw new AxiosError('409', '409', config as InternalAxiosRequestConfig, undefined, response);
    };
    fireEvent.click(row('e-1').getByRole('button', { name: 'Download' }));
    expect(await screen.findByText('This file is still being checked for malware. Try again in a minute.')).toHaveAttribute('data-problem-code', 'scan_pending');
  });

  it('reads the server’s file name from either form of the header', () => {
    expect(fileNameOf('attachment; filename="criteria.pdf"')).toBe('criteria.pdf');
    expect(fileNameOf("attachment; filename*=utf-8''f%C3%B6rslag%20v2.pdf")).toBe('förslag v2.pdf');
    expect(fileNameOf('attachment; filename="say \\"hi\\".txt"')).toBe('say "hi".txt');
    expect(fileNameOf(undefined)).toBeNull();
    expect(fileNameOf('attachment')).toBeNull();
  });

  it('lets go of the bytes once the browser has them', () => {
    const revoked = vi.fn();
    Object.assign(URL, { createObjectURL: () => 'blob:local/2', revokeObjectURL: revoked });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    saveDownload(new Blob(['x']), null);
    expect(revoked).toHaveBeenCalledWith('blob:local/2');
    expect(document.querySelector('a[download]')).toBeNull();
  });
});

describe('links', () => {
  it('open in a new tab only for an http or https address; anything else is plain text', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    const link = row('e-5').getByRole('link', { name: /Investment committee minutes/ });
    expect(link).toHaveAttribute('href', LINK.url);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(row('e-6').queryByRole('link')).toBeNull();
    expect(row('e-6').getByText(UNSAFE_LINK.name)).toBeInTheDocument();
  });
});

describe('who may do what', () => {
  it('a reader downloads and does nothing else', async () => {
    serve(() => undefined);
    renderPanel(READER);
    await screen.findByText(CLEAN.name);
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Attach evidence' })).toBeNull();
  });

  it('a contributor attaches but does not remove', async () => {
    serve(() => undefined);
    renderPanel(CONTRIBUTOR);
    await screen.findByText(CLEAN.name);
    expect(screen.getByRole('button', { name: 'Attach evidence' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
  });

  it('while the case waits for sign-off nothing is added or removed, and the panel says why', async () => {
    serve(() => undefined);
    renderPanel(WORKER, 'signoff');
    await screen.findByText(CLEAN.name);
    expect(screen.getByText(/can't be added or removed while the case waits for sign-off/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Attach evidence' })).toBeNull();
    expect(row('e-1').getByRole('button', { name: 'Download' })).toBeInTheDocument();
  });

  it('shows the empty state and the error with a retry', async () => {
    serve(() => undefined, []);
    renderPanel(WORKER, 'assessing');
    expect(await screen.findByText('No evidence yet')).toBeInTheDocument();
    cleanup();
    serve((sent) => (sent.path.endsWith('/evidence') ? { status: 500, data: {} } : undefined));
    renderPanel(READER);
    expect(await screen.findByText('Could not load the evidence')).toBeInTheDocument();
  });
});

describe('attaching', () => {
  async function openDialog() {
    await screen.findByText(CLEAN.name);
    fireEvent.click(screen.getByRole('button', { name: 'Attach evidence' }));
    return screen.findByRole('dialog', { name: 'Attach evidence' });
  }

  it('sends a file as one multipart post, shows its progress, and says it is being checked', async () => {
    let release: (answer: AxiosResponse) => void = () => undefined;
    const posted: FormData[] = [];
    serve(() => undefined);
    const fallback = api.defaults.adapter;
    api.defaults.adapter = async (config) => {
      if (config.method === 'post') {
        posted.push(config.data as FormData);
        config.onUploadProgress?.({ loaded: 206_000, total: 412_000, bytes: 206_000, lengthComputable: true });
        return new Promise((resolve) => {
          release = resolve;
        });
      }
      return (fallback as (c: InternalAxiosRequestConfig) => Promise<AxiosResponse>)(config);
    };
    renderPanel(CONTRIBUTOR);
    const dialog = await openDialog();
    const bytes = new File(['%PDF-1.7'], 'criteria.pdf', { type: 'application/pdf' });
    fireEvent.change(within(dialog).getByLabelText('File'), { target: { files: [bytes] } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));

    expect(await within(dialog).findByText('Uploading… 50%')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled();
    const form = posted[0] as FormData;
    expect([form.get('kind'), form.get('name'), form.get('url')]).toEqual(['file', 'criteria.pdf', null]);
    expect(form.get('file')).toBeInstanceOf(File);

    release({ data: { evidence: { ...CLEAN, scanState: 'pending' } }, status: 201, statusText: '201', headers: {}, config: {} as InternalAxiosRequestConfig });
    expect(await screen.findByText('Attached. It can be opened once it has been checked for malware.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(localStorage.length).toBe(0);
  });

  it('sends a link with its address and a reference with its name only', async () => {
    const sent: FormData[] = [];
    serve((request) => {
      if (request.method !== 'post') return undefined;
      sent.push(request.body as FormData);
      return { status: 201, data: { evidence: LINK } };
    });
    renderPanel(CONTRIBUTOR);
    let dialog = await openDialog();
    fireEvent.click(within(dialog).getByLabelText(/A link/));
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'IC minutes' } });
    fireEvent.change(within(dialog).getByLabelText('Web address'), { target: { value: 'https://intranet.bank.example/ic' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));
    expect(await screen.findByText('Attached.')).toBeInTheDocument();

    dialog = await openDialog();
    fireEvent.click(within(dialog).getByLabelText(/A reference/));
    fireEvent.change(within(dialog).getByLabelText('Document'), { target: { value: 'Inducements policy, section 4' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));
    await waitFor(() => expect(sent).toHaveLength(2));

    expect([sent[0]?.get('kind'), sent[0]?.get('name'), sent[0]?.get('url'), sent[0]?.get('file')]).toEqual(['link', 'IC minutes', 'https://intranet.bank.example/ic', null]);
    expect([sent[1]?.get('kind'), sent[1]?.get('name'), sent[1]?.get('url'), sent[1]?.get('file')]).toEqual(['reference', 'Inducements policy, section 4', null, null]);
  });

  it('quotes the server’s allow-list and cap from its refusal, and keeps the dialog open', async () => {
    const detail = 'This file cannot be attached. Attach a PDF, Word, Excel, PowerPoint, PNG, JPEG, text or CSV file of at most 25 MB whose name ends in its type.';
    serve((request) => (request.method === 'post' ? { status: 422, data: { code: 'validation_error', detail } } : undefined));
    renderPanel(CONTRIBUTOR);
    const dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText('File'), { target: { files: [new File(['PK'], 'notes.zip')] } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));
    expect(await within(dialog).findByText(detail)).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('says in words when no scanner can check a file, and the cap in the server’s words', async () => {
    serve((request) => (request.method === 'post' ? { status: 503, data: { code: 'scanner_unavailable', detail: 'x' } } : undefined));
    renderPanel(CONTRIBUTOR);
    let dialog = await openDialog();
    fireEvent.change(within(dialog).getByLabelText('File'), { target: { files: [new File(['%PDF'], 'a.pdf')] } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));
    expect(await within(dialog).findByText("Files can't be checked for malware right now, so nothing was attached. Try again later.")).toBeInTheDocument();

    cleanup();
    const cap = 'A case holds at most 100 pieces of evidence. Remove one to add another.';
    serve((request) => (request.method === 'post' ? { status: 409, data: { code: 'evidence_limit_reached', detail: cap } } : undefined));
    renderPanel(CONTRIBUTOR);
    dialog = await openDialog();
    fireEvent.click(within(dialog).getByLabelText(/A reference/));
    fireEvent.change(within(dialog).getByLabelText('Document'), { target: { value: 'Policy' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Attach evidence' }));
    expect(await within(dialog).findByText(cap)).toBeInTheDocument();
  });
});

describe('removing', () => {
  it('asks first, then removes it', async () => {
    const sent = serve((request) => (request.method === 'delete' ? { status: 204 } : undefined));
    renderPanel(WORKER);
    await screen.findByText(CLEAN.name);
    fireEvent.click(row('e-2').getByRole('button', { name: 'Remove' }));
    const dialog = await screen.findByRole('dialog', { name: `Remove "${PENDING.name}"?` });
    expect(writes(sent)).toEqual([]);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(writes(sent).map((request) => [request.method, request.path])).toEqual([['delete', '/api/v1/evidence/e-2']]));
  });
});

describe('formatSize', () => {
  it('reads kilobytes and megabytes in the reader’s language', () => {
    expect(formatSize(412_000, 'en-GB')).toBe('412 kB');
    expect(formatSize(2_100_000, 'en-GB')).toBe('2.1 MB');
    expect(formatSize(12, 'en-GB')).toBe('1 kB');
  });
});
