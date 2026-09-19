import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EmptyState } from './EmptyState';
import { PageHead } from './PageHead';

describe('EmptyState', () => {
  it('names the next action', () => {
    render(<EmptyState title="Nothing yet" body="Set it up first." action={{ label: 'Go to admin', href: '/admin' }} />);
    expect(screen.getByRole('heading', { level: 2, name: 'Nothing yet' })).toBeInTheDocument();
    expect(screen.getByText('Set it up first.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to admin' })).toHaveAttribute('href', '/admin');
  });

  it('renders without an action', () => {
    render(<EmptyState title="Nothing yet" body="Come back later." />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});

describe('PageHead', () => {
  it('renders kicker, title, lede and actions', () => {
    render(<PageHead kicker="Friday" title="Today" lede="One line." actions={<button type="button">act</button>} />);
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument();
    expect(screen.getByText('Friday')).toBeInTheDocument();
    expect(screen.getByText('One line.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'act' })).toBeInTheDocument();
  });

  it('renders the title alone', () => {
    render(<PageHead title="Today" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument();
  });
});
