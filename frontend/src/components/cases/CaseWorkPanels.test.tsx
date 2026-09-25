import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { CaseVocabularyRef, CaseWorkflow } from '@/features/cases/types';

import { CaseWorkPanels, casePanelsFor } from './CaseWorkPanels';

// Which panels a case shows, from its fixed category and, once closed, from
// its close reason's fixed kind (design/screens/tenant-change.html, "Shown
// while"). A dismissed case and a one-person close return to triage; a
// signed-off case ends on its sign-off.

const reason = (kind: string | null): CaseVocabularyRef => ({ key: `r_${kind}`, kind, label: 'Reason' });
const at = (category: CaseWorkflow['category'], closeReason: CaseVocabularyRef | null = null) => ({ category, closeReason, dismissedReason: null });

describe('casePanelsFor', () => {
  it('shows triage until the assessment starts, and the case file in every status', () => {
    expect(casePanelsFor(at('new'))).toEqual(['triage', 'caseFile']);
    expect(casePanelsFor(at('assigned'))).toEqual(['triage', 'caseFile']);
    expect(casePanelsFor(at('dismissed'))).toEqual(['triage', 'caseFile']);
  });

  it('adds the work from assessing on, with the one-person close still on triage while assessing', () => {
    expect(casePanelsFor(at('assessing'))).toEqual(['triage', 'assessment', 'actions', 'evidence', 'caseFile']);
    expect(casePanelsFor(at('implementing'))).toEqual(['assessment', 'actions', 'evidence', 'signoff', 'caseFile']);
    expect(casePanelsFor(at('signoff'))).toEqual(['assessment', 'actions', 'evidence', 'signoff', 'caseFile']);
  });

  it('a closed case follows its close reason’s kind', () => {
    expect(casePanelsFor(at('closed', reason('signed_off')))).toEqual(['assessment', 'actions', 'evidence', 'signoff', 'caseFile']);
    expect(casePanelsFor(at('closed', reason('no_action')))).toEqual(['triage', 'assessment', 'actions', 'evidence', 'caseFile']);
    expect(casePanelsFor(at('closed', reason('not_applicable')))).toEqual(['triage', 'assessment', 'actions', 'evidence', 'caseFile']);
  });

  it('a closed case whose kind is unknown offers neither a way back nor a sign-off', () => {
    expect(casePanelsFor(at('closed', reason(null)))).toEqual(['assessment', 'actions', 'evidence', 'caseFile']);
    expect(casePanelsFor(at('closed'))).toEqual(['assessment', 'actions', 'evidence', 'caseFile']);
  });
});

describe('CaseWorkPanels', () => {
  it('renders its panels, which render nothing until they are built', () => {
    const workflow = { ...at('closed', reason('signed_off')), id: 'case-1', version: 7 } as CaseWorkflow;
    const { container } = render(<CaseWorkPanels change={{ id: 'c-1' } as never} workflow={workflow} />);
    expect(container.querySelector('[data-case-panels="closed"]')).toBeEmptyDOMElement();
  });
});
