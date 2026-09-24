import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ChangeDetail } from '@/features/watch/api';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { PermissionsProvider } from '@/shared/navigation/require-permission';
import { installAdapter, queryWrapper, resetApiForTests, type Answer, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';
import { defaultFormatContext } from '@/shared/utils/format';

import { SoWhatPanel, soWhatOf, soWhatProvenance } from './SoWhatPanel';

// The "So what?" block of design/screens/tenant-change.html: machine output
// until a person here confirms it, drawn as a draft with the agent that
// wrote it named (WAT-05, D-66). A person holding cases.work confirms it or
// rewrites it for this bank alone; everyone else sees the label and no
// buttons.

const t = createT('en');
const ctx = defaultFormatContext;

const base = {
  id: 'c-1',
  soWhatDraft: 'Teams that pay for external research should confirm the criteria exist.',
  model: 'Research agent 0.4',
  case: {
    id: 'case-1',
    category: 'new',
    allowedTransitions: [],
    footprintMatch: true,
    obligationDecisions: [],
    ownerId: null,
    soWhatConfirmed: false,
    soWhatConfirmedAt: null,
    soWhatText: 'Confirm the annual assessment criteria with the research desk before 1 October.',
    urgency: null,
    urgencyConfirmed: false,
  },
} as unknown as ChangeDetail;

const confirmed = {
  ...base,
  case: { ...base.case!, soWhatConfirmed: true, soWhatConfirmedAt: '2026-09-17T09:12:00Z' },
} as ChangeDetail;

const SESSION = { user: { locale: 'en' }, tenant: { timezone: 'Europe/Stockholm' }, enrolmentPending: false, permissions: ['cases.work'] };
const SAVED = { caseId: 'case-1', changeId: 'c-1', text: 'Ours.', confirmed: true, confirmedAt: '2026-09-17T09:12:00Z', confirmedByName: 'Sara Lind', isAiDraft: false };

function renderPanel(change: ChangeDetail, permissions: string[] = []): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <PermissionsProvider permissions={permissions}>
          <SoWhatPanel change={change} />
        </PermissionsProvider>
      </LocaleProvider>
    </Query>,
  );
}

/** The session read answers a signed-in reader, every write answers `answer`; what is returned is the writes alone. */
function serve(answer: Answer): () => Sent[] {
  const sent = installAdapter((request) => (request.method === 'get' ? { status: 200, data: SESSION } : answer));
  return () => sent.filter((request) => request.method !== 'get');
}

describe('whose wording the panel shows', () => {
  it('shows this bank’s own copy where it has a case, and the library draft otherwise', () => {
    expect(soWhatOf(base).wording).toBe('Confirm the annual assessment criteria with the research desk before 1 October.');
    expect(soWhatOf({ ...base, case: null } as ChangeDetail).wording).toBe('Teams that pay for external research should confirm the criteria exist.');
  });

  it('a change no agent has read yet has no wording, and empty text is no wording', () => {
    expect(soWhatOf({ ...base, case: null, soWhatDraft: null } as ChangeDetail).wording).toBeNull();
    expect(soWhatOf({ ...base, case: { ...base.case!, soWhatText: '' } } as ChangeDetail).wording).toBeNull();
  });

  it('names the agent that drafted a draft, and only the confirmation once a person here stood behind it', () => {
    expect(soWhatProvenance(soWhatOf(base), t, ctx)).toEqual(['Drafted by Research agent 0.4, which read this change']);
    // A confirmed wording may be the bank's own rewrite, so the model is not named as its author.
    expect(soWhatProvenance(soWhatOf(confirmed), t, ctx)).toEqual(['Confirmed 17 Sept 2026']);
    expect(soWhatProvenance(soWhatOf({ ...base, model: null } as ChangeDetail), t, ctx)).toEqual(['Drafted by the agent that read this change']);
  });
});

describe('the So what panel', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('labels an unconfirmed wording as a draft and names where it came from', () => {
    renderPanel(base);
    expect(screen.getByText('Drafted by AI, not yet confirmed by a person')).toBeInTheDocument();
    expect(screen.getByText('Drafted by Research agent 0.4, which read this change')).toBeInTheDocument();
    expect(screen.getByText('So what?')).toBeInTheDocument();
  });

  it('a wording this bank confirmed loses the draft label and says when', () => {
    renderPanel(confirmed);
    expect(screen.queryByText('Drafted by AI, not yet confirmed by a person')).not.toBeInTheDocument();
    expect(screen.getByText('Confirmed 17 Sept 2026')).toBeInTheDocument();
  });

  it('a reader without cases.work sees the label and no buttons', () => {
    renderPanel(base, ['watch.read']);
    expect(screen.getByText('Drafted by AI, not yet confirmed by a person')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a change this bank has no case for offers no control, because there is nothing to write to', () => {
    renderPanel({ ...base, case: null } as ChangeDetail, ['cases.work']);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('"Confirm wording" stands behind the draft on this bank’s case, sending no text', async () => {
    const writes = serve({ status: 200, data: SAVED });
    renderPanel(base, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm wording' }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect([writes()[0]?.method, writes()[0]?.path, writes()[0]?.body]).toEqual(['post', '/api/v1/changes/c-1/so-what/confirm', null]);
  });

  it('a confirmed wording can still be rewritten, and is never confirmed twice', () => {
    renderPanel(confirmed, ['cases.work']);
    expect(screen.getByRole('button', { name: 'Rewrite' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm wording' })).not.toBeInTheDocument();
  });

  it('"Rewrite" starts from the wording shown and "Save and confirm" sends the bank’s own words', async () => {
    const writes = serve({ status: 200, data: SAVED });
    renderPanel(base, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Rewrite' }));

    const box = screen.getByRole('textbox', { name: 'So what?' });
    expect(box).toHaveValue('Confirm the annual assessment criteria with the research desk before 1 October.');
    expect(screen.getByText('Your wording replaces the draft for your organisation only. The draft stays in the AI log.')).toBeInTheDocument();
    fireEvent.change(box, { target: { value: '  Ours, for the research desk.  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save and confirm' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect([writes()[0]?.method, writes()[0]?.path, writes()[0]?.body]).toEqual(['put', '/api/v1/changes/c-1/so-what', { text: 'Ours, for the research desk.' }]);
    // Saved: the form closes onto the panel, which the re-read fills.
    await waitFor(() => expect(screen.queryByRole('textbox')).not.toBeInTheDocument());
  });

  it('an empty wording cannot be saved, and Cancel leaves the draft as it was', () => {
    const writes = serve({ status: 200, data: SAVED });
    renderPanel(base, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Rewrite' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'So what?' }), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: 'Save and confirm' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByText('Drafted by AI, not yet confirmed by a person')).toBeInTheDocument();
    expect(writes()).toHaveLength(0);
  });

  it('a save the server refuses keeps the form and says why', async () => {
    serve({ status: 422, data: { code: 'validation_error', detail: 'The wording is longer than 4000 characters.' } });
    renderPanel(base, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Rewrite' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save and confirm' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The wording is longer than 4000 characters.');
    expect(screen.getByRole('textbox', { name: 'So what?' })).toBeInTheDocument();
  });

  it('a confirmation the server refuses says why beside the draft', async () => {
    serve({ status: 404, data: { code: 'not_found', detail: 'Not found.' } });
    renderPanel(base, ['cases.work']);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm wording' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Not found.');
    expect(screen.getByText('Drafted by AI, not yet confirmed by a person')).toBeInTheDocument();
  });

  it('a change with no draft yet says so rather than showing an empty box', () => {
    renderPanel({ ...base, case: null, soWhatDraft: null } as ChangeDetail);
    expect(screen.getByText('No wording yet')).toBeInTheDocument();
    expect(screen.getByText('A draft appears here once the agent has read the change.')).toBeInTheDocument();
  });
});
