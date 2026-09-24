import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { queryWrapper } from '@/shared/testing/api-adapter';
import type { ObligationVersionRow } from '@/features/library/types';

import { VersionBar, asOfFor } from './VersionBar';

// The version bar (design/screens/tenant-obligation.html; INV-04, AC-INV1):
// choosing a version is choosing the date it was in force on, so the read
// stays the one source of truth.

const nobody = { verifiedOrigin: '', confirmedByAgent: null, proposedByAgent: null };
const first: ObligationVersionRow = { versionNumber: 1, effectiveFrom: null, effectiveTo: { date: '2026-09-30', precision: 'day' }, approvedAt: null, ...nobody };
const second: ObligationVersionRow = {
  versionNumber: 2,
  effectiveFrom: { date: '2026-10-01', precision: 'day' },
  effectiveTo: null,
  approvedAt: '2026-09-17T14:02:11Z',
  ...nobody,
  verifiedOrigin: 'user',
};

function renderIn(node: ReactNode) {
  const { wrapper } = queryWrapper();
  const Wrapper = wrapper as (props: { children: ReactNode }) => ReactNode;
  return render(<Wrapper>{<LocaleProvider locale="en">{node}</LocaleProvider>}</Wrapper>);
}

function renderBar(props: Partial<Parameters<typeof VersionBar>[0]> = {}) {
  const onAsOf = vi.fn();
  const onShowDiff = vi.fn();
  renderIn(<VersionBar versions={[first, second]} currentVersion={1} asOf="" onAsOf={onAsOf} showDiff={false} onShowDiff={onShowDiff} {...props} />);
  return { onAsOf, onShowDiff };
}

describe('asOfFor', () => {
  it('takes the day a version took effect, or the last day it was in force', () => {
    expect(asOfFor(second)).toBe('2026-10-01');
    expect(asOfFor(first)).toBe('2026-09-30');
    // The only version there is: today shows it, so the date is cleared.
    expect(asOfFor({ versionNumber: 1, effectiveFrom: null, effectiveTo: null, approvedAt: null, ...nobody })).toBe('');
  });
});

describe('VersionBar', () => {
  it('names each version with its effective date and presses the one on screen', () => {
    renderBar();
    expect(screen.getByRole('button', { name: 'Version 1' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Version 2, from 1 Oct 2026' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('reads the record as of the day a chosen version was in force', () => {
    const { onAsOf } = renderBar();
    fireEvent.click(screen.getByRole('button', { name: 'Version 2, from 1 Oct 2026' }));
    expect(onAsOf).toHaveBeenCalledWith('2026-10-01');
    fireEvent.change(screen.getByLabelText('As of'), { target: { value: '2026-06-30' } });
    expect(onAsOf).toHaveBeenCalledWith('2026-06-30');
  });

  it('offers "Show what changed" only where there is a version to compare against', () => {
    const { onShowDiff } = renderBar();
    fireEvent.click(screen.getByRole('button', { name: 'Show what changed' }));
    expect(onShowDiff).toHaveBeenCalledWith(true);
  });

  it('leaves the diff chip out of a record with one version, and presses nothing when no version is in force', () => {
    cleanup();
    renderIn(<VersionBar versions={[first]} currentVersion={null} asOf="2020-01-01" onAsOf={vi.fn()} showDiff={false} onShowDiff={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Show what changed' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Version 1' })).toHaveAttribute('aria-pressed', 'false');
  });
});
