"use client";

import { cn } from "@/lib/utils";
import {
  ChevronDownIcon,
  FilmIcon,
  MapPinIcon,
  PackageIcon,
  UserIcon,
} from "lucide-react";
import { useState } from "react";

// ---------------------------------------------------------------------------
// Types (matching backend StoryGraphViewDisplayBlock)
// ---------------------------------------------------------------------------

type StoryGraphEntity = {
  id: string;
  name: string;
  kind: "character" | "location" | "prop";
  reference_image?: string;
};

type StoryGraphShot = {
  shot_id: string;
  order: number;
  shot_type?: string;
  intent?: string;
  focus_on?: string[];
  techniques?: string[];
  video_clip?: string;
};

type StoryGraphEventData = {
  id: string;
  description?: string;
  happens_at?: string;
  character_ids?: string[];
  shots?: StoryGraphShot[];
};

export type StoryGraphViewData = {
  phase?: string;
  entities?: StoryGraphEntity[];
  timeline?: StoryGraphEventData[];
  parallel_groups?: string[][];
  summary?: Record<string, number>;
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const KindIcon = ({ kind }: { kind: string }) => {
  switch (kind) {
    case "character":
      return <UserIcon className="size-3 shrink-0" />;
    case "location":
      return <MapPinIcon className="size-3 shrink-0" />;
    case "prop":
      return <PackageIcon className="size-3 shrink-0" />;
    default:
      return null;
  }
};

const EntityCard = ({
  entity,
  serverBase,
}: {
  entity: StoryGraphEntity;
  serverBase: string;
}) => {
  const [imgError, setImgError] = useState(false);
  const imgSrc = entity.reference_image
    ? `${serverBase}/files/${encodeURIComponent(entity.reference_image)}`
    : "";

  return (
    <div className="flex flex-col items-center gap-1 w-16 shrink-0">
      <div className="relative size-12 rounded-md border border-border/40 bg-muted/30 overflow-hidden flex items-center justify-center">
        {imgSrc && !imgError ? (
          // biome-ignore lint/a11y/noNoninteractiveElementInteractions: lifecycle event
          <img
            src={imgSrc}
            alt={entity.name}
            className="size-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <KindIcon kind={entity.kind} />
        )}
      </div>
      <span className="text-[10px] text-muted-foreground text-center leading-tight line-clamp-2">
        {entity.name}
      </span>
    </div>
  );
};

const TechniqueBadge = ({ tech }: { tech: string }) => {
  const colors: Record<string, string> = {
    A: "bg-blue-500/20 text-blue-700 dark:text-blue-300",
    B: "bg-purple-500/20 text-purple-700 dark:text-purple-300",
    C: "bg-green-500/20 text-green-700 dark:text-green-300",
  };
  const labels: Record<string, string> = {
    A: "Ref",
    B: "Gen",
    C: "Cont",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1 py-0.5 text-[9px] font-medium",
        colors[tech] ?? "bg-muted text-muted-foreground",
      )}
      title={
        tech === "A"
          ? "Reference images"
          : tech === "B"
            ? "First-frame generation"
            : tech === "C"
              ? "Tail-frame continuity"
              : tech
      }
    >
      {labels[tech] ?? tech}
    </span>
  );
};

const ShotRow = ({ shot }: { shot: StoryGraphShot }) => (
  <div className="flex items-center gap-2 py-1 px-2 text-xs">
    <FilmIcon className="size-3 shrink-0 text-muted-foreground" />
    <span className="text-muted-foreground min-w-[2ch]">#{shot.order}</span>
    {shot.shot_type && (
      <span className="rounded bg-muted/60 px-1 py-0.5 text-[10px]">
        {shot.shot_type}
      </span>
    )}
    {shot.intent && (
      <span className="flex-1 text-muted-foreground truncate text-[10px]">
        {shot.intent}
      </span>
    )}
    <div className="flex items-center gap-0.5">
      {shot.techniques?.map((t) => <TechniqueBadge key={t} tech={t} />)}
    </div>
  </div>
);

const EventCard = ({
  event,
  entityMap,
  isParallel,
}: {
  event: StoryGraphEventData;
  entityMap: Map<string, StoryGraphEntity>;
  isParallel: boolean;
}) => {
  const [expanded, setExpanded] = useState(false);
  const shots = event.shots ?? [];
  const hasShots = shots.length > 0;

  const locationName = event.happens_at
    ? (entityMap.get(event.happens_at)?.name ?? event.happens_at)
    : "";

  const charNames = (event.character_ids ?? [])
    .map((id) => entityMap.get(id)?.name ?? id)
    .join(", ");

  return (
    <div
      className={cn(
        "rounded-md border border-border/40 bg-card/20 overflow-hidden",
        isParallel && "border-l-2 border-l-amber-500/60",
      )}
    >
      {/* Header */}
      <button
        type="button"
        className={cn(
          "flex w-full items-start gap-2 px-3 py-2 text-left",
          hasShots && "cursor-pointer hover:bg-muted/30",
        )}
        onClick={() => hasShots && setExpanded(!expanded)}
        disabled={!hasShots}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono text-muted-foreground/60">
              {event.id}
            </span>
            {isParallel && (
              <span className="text-[9px] text-amber-600 dark:text-amber-400 font-medium">
                PARALLEL
              </span>
            )}
          </div>
          {event.description && (
            <div className="text-xs mt-0.5 line-clamp-2">
              {event.description}
            </div>
          )}
          <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
            {locationName && (
              <span className="flex items-center gap-0.5">
                <MapPinIcon className="size-2.5" />
                {locationName}
              </span>
            )}
            {charNames && (
              <span className="flex items-center gap-0.5">
                <UserIcon className="size-2.5" />
                {charNames}
              </span>
            )}
          </div>
        </div>
        {hasShots && (
          <div className="flex items-center gap-1 shrink-0 mt-0.5">
            <span className="text-[10px] text-muted-foreground">
              {shots.length} shot{shots.length > 1 ? "s" : ""}
            </span>
            <ChevronDownIcon
              className={cn(
                "size-3 text-muted-foreground transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </div>
        )}
      </button>

      {/* Shots */}
      {expanded && hasShots && (
        <div className="border-t border-border/40 divide-y divide-border/20">
          {shots.map((shot) => (
            <ShotRow key={shot.shot_id} shot={shot} />
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const StoryGraphView = ({ data }: { data: StoryGraphViewData }) => {
  const entities = data.entities ?? [];
  const timeline = data.timeline ?? [];
  const parallelGroups = data.parallel_groups ?? [];
  const summary = data.summary ?? {};

  // Build entity lookup
  const entityMap = new Map<string, StoryGraphEntity>();
  for (const e of entities) {
    entityMap.set(e.id, e);
  }

  // Build parallel event set
  const parallelEventSet = new Set<string>();
  for (const group of parallelGroups) {
    for (const eid of group) {
      parallelEventSet.add(eid);
    }
  }

  const characters = entities.filter((e) => e.kind === "character");
  const locations = entities.filter((e) => e.kind === "location");
  const props = entities.filter((e) => e.kind === "prop");

  // Determine server base from current page URL
  const serverBase = typeof window !== "undefined" ? window.location.origin : "";

  return (
    <div className="my-2 rounded-md border border-border/50 bg-card/10 overflow-hidden">
      {/* Summary bar */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border/40 bg-muted/20 text-[10px] text-muted-foreground">
        <span className="font-medium text-foreground text-xs">Story Graph</span>
        {summary.characters != null && (
          <span>{summary.characters} characters</span>
        )}
        {summary.locations != null && (
          <span>{summary.locations} locations</span>
        )}
        {summary.events != null && <span>{summary.events} events</span>}
        {summary.shots != null && summary.shots > 0 && (
          <span>{summary.shots} shots</span>
        )}
        {data.phase && (
          <span className="ml-auto rounded bg-muted/60 px-1.5 py-0.5 text-[9px]">
            {data.phase}
          </span>
        )}
      </div>

      {/* Entity rows */}
      {(characters.length > 0 || locations.length > 0 || props.length > 0) && (
        <div className="px-3 py-2 border-b border-border/40 space-y-2">
          {characters.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Characters
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {characters.map((e) => (
                  <EntityCard key={e.id} entity={e} serverBase={serverBase} />
                ))}
              </div>
            </div>
          )}
          {locations.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Locations
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {locations.map((e) => (
                  <EntityCard key={e.id} entity={e} serverBase={serverBase} />
                ))}
              </div>
            </div>
          )}
          {props.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Props
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {props.map((e) => (
                  <EntityCard key={e.id} entity={e} serverBase={serverBase} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Timeline */}
      {timeline.length > 0 && (
        <div className="px-3 py-2 space-y-2">
          <div className="text-[10px] text-muted-foreground/60">
            Timeline ({timeline.length} events)
          </div>
          {timeline.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              entityMap={entityMap}
              isParallel={parallelEventSet.has(event.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};
