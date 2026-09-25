import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { LegalText } from './LegalText';

function renderIn(locale: 'en' | 'sv', node: ReactNode) {
  return render(<LocaleProvider locale={locale}>{node}</LocaleProvider>);
}

describe('LegalText', () => {
  it('sets the text in its own language beside a sand margin with a brass section sign', () => {
    const { container } = renderIn(
      'en',
      <LegalText lang="sv" reference="9 kap. 6 §">
        Investeringsanalys från tredje part får tas emot endast om den betalas med egna medel.
      </LegalText>,
    );
    const text = screen.getByText(/^Investeringsanalys från tredje part/);
    expect(text).toHaveAttribute('lang', 'sv');
    const margin = container.querySelector('[data-legal-margin]');
    expect(margin).toHaveClass('bg-sand', 'text-brass');
    const sign = margin?.querySelector('[aria-hidden="true"]');
    expect(sign).toHaveTextContent('§');
    expect(sign).toHaveClass('font-mono');
    expect(margin).toHaveTextContent('9 kap. 6 §');
  });

  it('the original carries no label', () => {
    const { container } = renderIn('en', <LegalText lang="sv">Originaltext.</LegalText>);
    expect(container.querySelector('[data-machine-translation]')).toBeNull();
    expect(screen.queryByText(/Machine translation/)).toBeNull();
  });

  it('a machine translation carries its label above the text, in the user language and outside the text language', () => {
    renderIn(
      'en',
      <LegalText lang="en" translatedFrom="sv">
        Research from third parties may be received only if it is paid from own resources.
      </LegalText>,
    );
    const label = screen.getByText('Machine translation from Swedish. The original is authoritative.');
    expect(label).toHaveAttribute('data-machine-translation');
    expect(label.closest('[lang]')).toBeNull();
    expect(screen.getByText(/^Research from third parties/)).toHaveAttribute('lang', 'en');
  });

  it('reads the label in Swedish for a Swedish user', () => {
    renderIn(
      'sv',
      <LegalText lang="en" translatedFrom="sv">
        Research.
      </LegalText>,
    );
    expect(screen.getByText('Maskinöversättning från svenska. Originalet gäller.')).toBeInTheDocument();
  });

  it('renders without a reference', () => {
    const { container } = renderIn('en', <LegalText lang="en">Text.</LegalText>);
    expect(container.querySelector('[data-legal-margin]')).toHaveTextContent(/^§$/);
  });
});
