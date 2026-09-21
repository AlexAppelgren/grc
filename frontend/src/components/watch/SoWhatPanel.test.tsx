import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ChangeDetail } from '@/features/watch/api';
import { createT } from '@/shared/i18n';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { queryWrapper } from '@/shared/testing/api-adapter';
import { defaultFormatContext } from '@/shared/utils/format';

import { SoWhatPanel, soWhatOf, soWhatProvenance } from './SoWhatPanel';

// The "So what?" block of design/screens/tenant-change.html: machine output
// until a person here confirms it, drawn as a draft with the agent that
// wrote it named (WAT-05, D-66). The confirm and rewrite controls are not
// built: who confirms a fact is an open question for the owner.

const t = createT('en');
const ctx = defaultFormatContext;

const base = {
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

function renderPanel(change: ChangeDetail): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <SoWhatPanel change={change} />
      </LocaleProvider>
    </Query>,
  );
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

  it('names the agent that drafted it, and says when a person here stood behind it', () => {
    expect(soWhatProvenance(soWhatOf(base), t, ctx)).toEqual(['Drafted by Research agent 0.4, which read this change']);
    expect(soWhatProvenance(soWhatOf(confirmed), t, ctx)).toEqual(['Drafted by Research agent 0.4, which read this change', 'Confirmed 17 Sept 2026']);
    expect(soWhatProvenance(soWhatOf({ ...base, model: null } as ChangeDetail), t, ctx)).toEqual(['Drafted by the agent that read this change']);
  });
});

describe('the So what panel', () => {
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

  it('offers no control: who may confirm a drafted fact is not decided', () => {
    renderPanel(base);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('a change with no draft yet says so rather than showing an empty box', () => {
    renderPanel({ ...base, case: null, soWhatDraft: null } as ChangeDetail);
    expect(screen.getByText('No wording yet')).toBeInTheDocument();
    expect(screen.getByText('A draft appears here once the agent has read the change.')).toBeInTheDocument();
  });
});
