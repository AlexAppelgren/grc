import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { createElement, type ReactNode } from 'react';

import { api, pathOf, resetApiClientForTests } from '@/shared/utils/api-client';

// Test support: the adapter replaces the network for the one axios instance.
// Each test scripts what the server answers per call and reads what the
// client sent. Not a mock of the API contract: the journeys prove that.

export interface Sent {
  method: string;
  path: string;
  body: unknown;
  params: unknown;
  authorization: string | undefined;
}

export interface Answer {
  status: number;
  data?: unknown;
}

function parseBody(data: unknown): unknown {
  if (typeof data !== 'string') return data ?? null;
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

export function installAdapter(script: (sent: Sent, index: number) => Answer): Sent[] {
  const sent: Sent[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const record: Sent = {
      method: (config.method ?? 'get').toLowerCase(),
      path: pathOf(config),
      body: parseBody(config.data),
      params: config.params ?? null,
      authorization: config.headers.get('Authorization') as string | undefined,
    };
    sent.push(record);
    const answer = script(record, sent.length - 1);
    const response: AxiosResponse = { data: answer.data ?? {}, status: answer.status, statusText: String(answer.status), headers: {}, config: config as InternalAxiosRequestConfig };
    if (answer.status >= 400) {
      throw new AxiosError(`status ${answer.status}`, String(answer.status), config as InternalAxiosRequestConfig, undefined, response);
    }
    return response;
  };
  api.defaults.adapter = adapter;
  return sent;
}

export function resetApiForTests(): void {
  resetApiClientForTests();
}

export function queryWrapper(): { wrapper: ({ children }: { children: ReactNode }) => ReactNode; queryClient: QueryClient } {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, queryClient };
}
