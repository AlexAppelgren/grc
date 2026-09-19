import { fireEvent, render, screen } from '@testing-library/react';
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import { Button, ButtonBar } from './Button';
import { CheckGroup, CheckRow, Field, Select, TextArea, TextInput } from './Field';
import { Modal } from './Modal';
import { Meta, Panel, Row, Rows } from './Panel';
import { ErrorState, LoadingState, NotFoundScreen, ProblemAlert, StatusLine } from './States';

// The prototype primitives the chunk 1 screens share: shape, states and the
// problem alert's branches. Copy is read from the English catalog.

function axiosError(status: number | undefined, data: unknown): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const response = status === undefined ? undefined : ({ status, data, statusText: '', headers: {}, config } as AxiosResponse);
  return new AxiosError('x', String(status), config, undefined, response);
}

describe('Button and ButtonBar', () => {
  it('renders the variants and sizes as a button of type button by default', () => {
    render(
      <ButtonBar>
        <Button variant="ghost" size="small">
          one
        </Button>
        <Button variant="danger">two</Button>
        <Button type="submit">three</Button>
      </ButtonBar>,
    );
    expect(screen.getByRole('button', { name: 'one' })).toHaveAttribute('type', 'button');
    expect(screen.getByRole('button', { name: 'three' })).toHaveAttribute('type', 'submit');
    expect(screen.getByRole('button', { name: 'two' }).className).toContain('text-negative');
    // The primary is last in DOM order, so it sits on the right (playbook 6.8).
    const buttons = screen.getAllByRole('button');
    expect(buttons.at(-1)).toHaveTextContent('three');
  });
});

describe('Field family', () => {
  it('wires label, hint and error to the control', () => {
    render(
      <Field id="f" label="Name" hint="Real constraint" error="Missing">
        <TextInput id="f" placeholder="e.g. x" />
      </Field>,
    );
    expect(screen.getByLabelText('Name')).toHaveAttribute('placeholder', 'e.g. x');
    expect(screen.getByText('Real constraint')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Missing');
  });

  it('renders a bare field and a bare group without hint or error', () => {
    render(
      <>
        <Field id="bare" label="Bare">
          <TextInput id="bare" />
        </Field>
        <CheckGroup legend="Group">
          <CheckRow id="c" label="Only" checked={false} />
        </CheckGroup>
      </>,
    );
    expect(screen.getByLabelText('Bare')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Only'));
  });

  it('renders textarea and select', () => {
    render(
      <>
        <TextArea aria-label="notes" />
        <Select aria-label="pick">
          <option value="a">A</option>
        </Select>
      </>,
    );
    expect(screen.getByLabelText('notes').tagName).toBe('TEXTAREA');
    expect(screen.getByLabelText('pick').tagName).toBe('SELECT');
  });

  it('check rows report changes and a group shows its error', () => {
    const onChange = vi.fn();
    render(
      <CheckGroup legend="Roles" hint="Pick some" error="Pick at least one role.">
        <CheckRow id="r1" label="Reader" hint="Reads" checked={false} onChange={onChange} />
        <CheckRow id="r2" label="Admin" checked disabled />
      </CheckGroup>,
    );
    fireEvent.click(screen.getByLabelText(/Reader/));
    expect(onChange).toHaveBeenCalledWith(true);
    expect(screen.getByLabelText(/Admin/)).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Pick at least one role.');
    expect(screen.getByText('Pick some')).toBeInTheDocument();
  });
});

describe('Panel, Rows, Row, Meta', () => {
  it('renders a titled panel, a sand panel and rows', () => {
    render(
      <>
        <Panel title="Profile">body</Panel>
        <Panel sand>sand</Panel>
        <Rows>
          <Row>
            <Meta>meta</Meta>
          </Row>
        </Rows>
      </>,
    );
    expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByText('sand').className).toContain('bg-sand');
    expect(screen.getByText('meta')).toBeInTheDocument();
  });
});

describe('Modal', () => {
  it('renders an accessible dialog with title and description when open', () => {
    const onOpenChange = vi.fn();
    render(
      <Modal open onOpenChange={onOpenChange} title="Confirm with your passkey" description="Body">
        <p>inside</p>
      </Modal>,
    );
    expect(screen.getByRole('dialog', { name: 'Confirm with your passkey' })).toBeInTheDocument();
    expect(screen.getByText('Body')).toBeInTheDocument();
    expect(screen.getByText('inside')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders nothing when closed', () => {
    render(
      <Modal open={false} onOpenChange={() => undefined} title="x">
        <p>inside</p>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('States', () => {
  it('loading, error and not found', () => {
    const onRetry = vi.fn();
    render(
      <>
        <LoadingState rows={3} />
        <ErrorState title="Could not load" onRetry={onRetry} />
        <NotFoundScreen />
      </>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.getByRole('heading', { name: 'Not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Today' })).toHaveAttribute('href', '/');
  });

  it('error state without retry and not found with its own copy', () => {
    render(
      <>
        <ErrorState title="Nope" />
        <NotFoundScreen body="No such member" backHref="/admin/members" backLabel="Members" />
        <StatusLine tone="positive">Saved.</StatusLine>
      </>,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('No such member')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Members' })).toHaveAttribute('href', '/admin/members');
    expect(screen.getByRole('status')).toHaveTextContent('Saved.');
  });

  it('ProblemAlert renders the server detail, the known code, the 403 grant, network and generic', () => {
    const { rerender } = render(<ProblemAlert error={axiosError(409, { code: 'last_admin', detail: 'Server says' })} codes={{ last_admin: 'Give someone else that role first.' }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Give someone else that role first.');
    rerender(<ProblemAlert error={axiosError(409, { code: 'other', detail: 'Server says' })} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Server says');
    rerender(<ProblemAlert error={axiosError(403, { code: 'permission_denied', detail: 'Only security', requiredPermission: 'security.manage' })} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Only security Needs security manage');
    rerender(<ProblemAlert error={axiosError(403, { code: 'permission_denied' })} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Your role does not include what this page needs.');
    rerender(<ProblemAlert error={axiosError(undefined, undefined)} />);
    expect(screen.getByRole('alert')).toHaveTextContent('The server could not be reached.');
    rerender(<ProblemAlert error={axiosError(500, {})} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong. Try again.');
    rerender(<ProblemAlert error={new Error('boom')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('boom');
    rerender(<ProblemAlert error={new Error('')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong. Try again.');
    rerender(<ProblemAlert error={axiosError(409, { code: 'x' })} className="custom" />);
    expect(screen.getByRole('alert').className).toBe('custom');
    rerender(<ProblemAlert error={null} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    rerender(<ProblemAlert error={undefined} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
