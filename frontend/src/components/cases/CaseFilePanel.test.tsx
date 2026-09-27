import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CaseWorkflow } from '@/features/cases/types';
import type { ChangeDetail } from '@/features/watch/api';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { setStepUpHandler, tokenStore } from '@/shared/utils/api-client';

import { CaseFilePanel, caseFileSections } from './CaseFilePanel';

// Show case file and Export on the change page (CAS-07; design/screens/
// tenant-change.html, "Show case file"). The text is the server's, in the
// reader's language with the bank's own clock: the panel only splits it at
// its headings and sets a hash in monospace. Export turns the same text into
// a file through the exports job, offered only to someone holding
// exports.create.

const HASH = '3f9a0c6e1b27d48f5a90c2e7b4d13f86a2c95e0b7d41f3a6c8e29b05d7f1c21e';
const TEXT = [
  'Case file: FI adopts amended rules on paying for investment research',
  'Authority: Finansinspektionen',
  '',
  'Evidence',
  '========',
  '- research-assessment-criteria-v2.pdf (file)',
  `  Content hash (SHA-256): ${HASH}`,
  '',
  'Sign-off',
  '========',
  'Requested by Sara Lindqvist on 2026-09-19 16:05 UTC+02:00.',
  'Signed off by Maria Ek on 2026-09-22 10:31 UTC+02:00.',
  '',
].join('\n');

const change = { id: 'c-1' } as ChangeDetail;
const workflow = {
  id: 'case-1',
  category: 'closed',
  version: 6,
} as unknown as CaseWorkflow;
const SESSION = {
  user: { id: 'u-1', locale: 'en' },
  tenant: { timezone: 'Europe/Stockholm' },
  enrolmentPending: false,
  permissions: [],
};
const JOB = {
  id: 'exp-1',
  kind: 'case_file',
  subjectId: 'case-1',
  format: 'txt',
  createdAt: '2026-09-22T08:40:00Z',
  completedAt: null,
  expiresAt: null,
  contentHash: null,
  downloadedAt: null,
  error: null,
};
const DONE = {
  ...JOB,
  status: 'succeeded',
  completedAt: '2026-09-22T08:40:05Z',
  expiresAt: '2026-09-29T08:40:05Z',
  contentHash: HASH,
};

function serve(route: (sent: Sent) => Answer | undefined): Sent[] {
  return installAdapter((request) => route(request) ?? (request.path === '/api/v1/me' ? { status: 200, data: SESSION } : { status: 404, data: { code: 'not_found' } }));
}

function renderPanel(permissions: string[]): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <CaseFilePanel change={change} workflow={workflow} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

const caseFile = (request: Sent): Answer | undefined => (request.path === '/api/v1/changes/c-1/case-file' ? { status: 200, data: TEXT } : undefined);

async function openFile(): Promise<HTMLElement> {
  fireEvent.click(screen.getByRole('button', { name: 'Show case file' }));
  return screen.findByRole('dialog', { name: 'Case file' });
}

beforeEach(() => {
  resetApiForTests();
  tokenStore.set('tok');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('caseFileSections', () => {
  it('splits the text at its underlined headings and keeps every other line as written', () => {
    expect(caseFileSections(TEXT)).toEqual([
      {
        heading: null,
        lines: ['Case file: FI adopts amended rules on paying for investment research', 'Authority: Finansinspektionen'],
      },
      {
        heading: 'Evidence',
        lines: ['- research-assessment-criteria-v2.pdf (file)', `  Content hash (SHA-256): ${HASH}`],
      },
      {
        heading: 'Sign-off',
        lines: ['Requested by Sara Lindqvist on 2026-09-19 16:05 UTC+02:00.', 'Signed off by Maria Ek on 2026-09-22 10:31 UTC+02:00.'],
      },
    ]);
  });

  it('a line of equals signs under nothing is text, not a heading', () => {
    expect(caseFileSections('====\nplain')).toEqual([{ heading: null, lines: ['====', 'plain'] }]);
  });
});

describe('Show case file', () => {
  it('reads nothing until it is opened, then shows the server’s text in sections with the hash in monospace', async () => {
    const sent = serve(caseFile);
    renderPanel(['cases.read']);
    expect(sent.some((request) => request.path.endsWith('/case-file'))).toBe(false);
    const dialog = await openFile();
    expect(await within(dialog).findByRole('heading', { name: 'Evidence' })).toBeInTheDocument();
    expect(within(dialog).getByRole('heading', { name: 'Sign-off' })).toBeInTheDocument();
    expect(within(dialog).getByText('Signed off by Maria Ek on 2026-09-22 10:31 UTC+02:00.')).toBeInTheDocument();
    const hash = within(dialog).getByText(HASH);
    expect(hash.tagName).toBe('CODE');
    expect(hash).toHaveClass('font-mono');
  });

  it('a case file that could not be read says so and offers to try again', async () => {
    let calls = 0;
    serve((request) => {
      if (!request.path.endsWith('/case-file')) return undefined;
      calls += 1;
      return calls === 1 ? { status: 500, data: { code: 'server_error' } } : { status: 200, data: TEXT };
    });
    renderPanel(['cases.read']);
    const dialog = await openFile();
    expect(await within(dialog).findByText('Could not load the case file')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Try again' }));
    expect(await within(dialog).findByRole('heading', { name: 'Evidence' })).toBeInTheDocument();
  });

  it('offers no Export without exports.create', async () => {
    serve(caseFile);
    renderPanel(['cases.read']);
    const dialog = await openFile();
    await within(dialog).findByRole('heading', { name: 'Evidence' });
    expect(within(dialog).queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });

  it('without cases.read there is nothing to show', () => {
    serve(caseFile);
    renderPanel(['watch.read']);
    expect(screen.queryByRole('button', { name: 'Show case file' })).not.toBeInTheDocument();
  });
});

describe('Export', () => {
  it('asks for a text export of this case, follows the job and downloads the file', async () => {
    const createObjectURL = vi.fn(() => 'blob:case-file');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const sent = serve((request) => {
      if (request.method === 'post' && request.path === '/api/v1/exports') return { status: 202, data: { ...JOB, status: 'queued' } };
      if (request.path === '/api/v1/exports/exp-1') return { status: 200, data: DONE };
      if (request.path === '/api/v1/exports/exp-1/download') return { status: 200, data: TEXT };
      return caseFile(request);
    });
    renderPanel(['cases.read', 'exports.create']);
    const dialog = await openFile();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export' }));
    expect(await within(dialog).findByText('The file is ready.')).toBeInTheDocument();
    expect(sent.find((request) => request.method === 'post')).toMatchObject({
      body: { kind: 'case_file', subjectId: 'case-1', format: 'txt' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Download the case file' }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(sent.some((request) => request.path === '/api/v1/exports/exp-1/download')).toBe(true);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:case-file');
  });

  it('says it is preparing the file while the job runs', async () => {
    serve((request) => {
      if (request.method === 'post' && request.path === '/api/v1/exports') return { status: 202, data: { ...JOB, status: 'queued' } };
      if (request.path === '/api/v1/exports/exp-1') return { status: 200, data: { ...JOB, status: 'running' } };
      return caseFile(request);
    });
    renderPanel(['cases.read', 'exports.create']);
    const dialog = await openFile();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export' }));
    expect(await within(dialog).findByText('Preparing the file…')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Download the case file' })).not.toBeInTheDocument();
  });

  it('a job that failed says the file could not be prepared', async () => {
    serve((request) => {
      if (request.method === 'post' && request.path === '/api/v1/exports') return { status: 202, data: { ...JOB, status: 'queued' } };
      if (request.path === '/api/v1/exports/exp-1')
        return {
          status: 200,
          data: { ...JOB, status: 'failed', error: 'builder failed' },
        };
      return caseFile(request);
    });
    renderPanel(['cases.read', 'exports.create']);
    const dialog = await openFile();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The file could not be prepared. Try again.');
  });

  it('a cancelled passkey prompt exports nothing, and says so', async () => {
    setStepUpHandler(() => Promise.resolve(false));
    const sent = serve((request) => {
      if (request.method === 'post' && request.path === '/api/v1/exports')
        return {
          status: 403,
          data: { status: 403, code: 'step_up_required', detail: '' },
        };
      return caseFile(request);
    });
    renderPanel(['cases.read', 'exports.create']);
    const dialog = await openFile();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Nothing was exported. Export needs your passkey.');
    expect(sent.some((request) => request.path.startsWith('/api/v1/exports/'))).toBe(false);
  });

  it('a file no longer kept asks for a new export', async () => {
    serve((request) => {
      if (request.method === 'post' && request.path === '/api/v1/exports') return { status: 202, data: { ...JOB, status: 'queued' } };
      if (request.path === '/api/v1/exports/exp-1') return { status: 200, data: DONE };
      if (request.path === '/api/v1/exports/exp-1/download')
        return {
          status: 409,
          data: { status: 409, code: 'export_expired', detail: '' },
        };
      return caseFile(request);
    });
    renderPanel(['cases.read', 'exports.create']);
    const dialog = await openFile();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Export' }));
    fireEvent.click(
      await within(dialog).findByRole('button', {
        name: 'Download the case file',
      }),
    );
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('The file is no longer kept. Export it again.');
  });
});
