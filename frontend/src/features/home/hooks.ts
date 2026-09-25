'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';

import * as home from './api';
import type { Briefing, Home, Roadmap, RoadmapQuery } from './types';

// Query keys and reads for Today, the roadmap and the weekly briefing
// (playbook 6.1). Nothing here writes.

export const homeKeys = {
  home: ['home'] as const,
  roadmap: (query: RoadmapQuery) => ['home', 'roadmap', query] as const,
  briefingCurrent: ['home', 'briefing', 'current'] as const,
  briefing: (weekStart: string) => ['home', 'briefing', weekStart] as const,
};

export function useHome(): UseQueryResult<Home> {
  return useQuery({ queryKey: homeKeys.home, queryFn: home.getHome });
}

export function useRoadmap(query: RoadmapQuery = {}): UseQueryResult<Roadmap> {
  return useQuery({ queryKey: homeKeys.roadmap(query), queryFn: () => home.getRoadmap(query) });
}

export function useCurrentBriefing(enabled = true): UseQueryResult<Briefing> {
  return useQuery({ queryKey: homeKeys.briefingCurrent, queryFn: home.getCurrentBriefing, enabled });
}

/** `weekStart` is `undefined` for the running week, read by `useCurrentBriefing` instead. */
export function useBriefing(weekStart: string, enabled = true): UseQueryResult<Briefing> {
  return useQuery({ queryKey: homeKeys.briefing(weekStart), queryFn: () => home.getBriefing(weekStart), enabled });
}
