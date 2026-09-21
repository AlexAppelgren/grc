import { serializeQuery } from '@/features/watch/api';
import { api } from '@/shared/utils/api-client';

import type { Briefing, Home, Roadmap, RoadmapQuery } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). Every read here is a
// GET that writes nothing; `GET /home` fans out its own four reads on the
// server, so the screen makes one call and chains nothing behind it.

const HOME = '/api/v1/home';
const ROADMAP = '/api/v1/roadmap';
const BRIEFINGS = '/api/v1/briefings';

export async function getHome(): Promise<Home> {
  return (await api.get<Home>(HOME)).data;
}

export async function getRoadmap(query: RoadmapQuery = {}): Promise<Roadmap> {
  return (await api.get<Roadmap>(ROADMAP, { params: query, paramsSerializer: { serialize: serializeQuery } })).data;
}

export async function getCurrentBriefing(): Promise<Briefing> {
  return (await api.get<Briefing>(`${BRIEFINGS}/current`)).data;
}

/** `weekStart` is the Monday of the week, `YYYY-MM-DD` (HOM-S3). */
export async function getBriefing(weekStart: string): Promise<Briefing> {
  return (await api.get<Briefing>(`${BRIEFINGS}/${weekStart}`)).data;
}
