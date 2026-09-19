import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LocaleProvider, useLocale, useT } from './LocaleProvider';

function Probe() {
  const t = useT();
  const locale = useLocale();
  return (
    <p>
      {locale}:{t('nav.today')}
    </p>
  );
}

describe('LocaleProvider', () => {
  it('defaults to the configured locale without a provider', () => {
    render(<Probe />);
    expect(screen.getByText('en:Today')).toBeInTheDocument();
  });

  it('hands the chosen locale and its t to children', () => {
    render(
      <LocaleProvider locale="sv">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByText('sv:Idag')).toBeInTheDocument();
  });
});
