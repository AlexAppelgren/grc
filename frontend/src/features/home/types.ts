// The home feature's names for the chunk 6 contract (Today, the roadmap and the weekly
// briefing): every shape is an alias over the generated schemas in
// src/types/api.generated.ts (from the backend's OpenAPI export; `bash generate-types.sh`
// regenerates them), never redeclared (playbook 6.1).

import type { components, operations } from '@/types/api.generated';

type Schemas = components['schemas'];

export type Home = Schemas['Home'];
export type HomeSourceHealth = Schemas['HomeSourceHealth'];

export type RoadmapItem = Schemas['HomeRoadmapItem'];
export type Roadmap = Schemas['HomeRoadmap'];
/** `GET /roadmap`'s three filters, exactly as the route declares them. */
export type RoadmapQuery = NonNullable<operations['getRoadmap']['parameters']['query']>;
export type RoadmapItemKind = RoadmapItem['kind'];

export type Briefing = Schemas['HomeBriefing'];
