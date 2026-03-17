"use client";

import { cn } from "@/lib/utils";
import {
  BrainIcon,
  ChevronDownIcon,
  ClockIcon,
  FilmIcon,
  MapPinIcon,
  MessageCircleIcon,
  Music2Icon,
  PackageIcon,
  PaletteIcon,
  PlayIcon,
  RatioIcon,
  UserIcon,
  Volume2Icon,
  WavesIcon,
} from "lucide-react";
import { useRef, useState } from "react";

// ---------------------------------------------------------------------------
// Types (matching backend StoryGraphViewDisplayBlock)
// ---------------------------------------------------------------------------

type StoryGraphProductionStyle = {
  id: string;
  description?: string;
  style_prefix?: string;
  negative_prefix?: string;
  aspect_ratio?: string;
  duration?: string;
};

type StoryGraphState = {
  id: string;
  phase?: string;
  reference_image?: string;
  description?: string;
  generation_prompt?: string;
};

type StoryGraphEntity = {
  id: string;
  name: string;
  kind: "character" | "location" | "prop";
  reference_image?: string;
  description?: string;
  generation_prompt?: string;
  states?: StoryGraphState[];
};

type StoryGraphShot = {
  shot_id: string;
  order: number;
  shot_type?: string;
  intent?: string;
  focus_on?: string[];
  techniques?: string[];
  video_clip?: string;
  reference_images?: string[];
  first_frame?: string;
  tail_frame?: string;
};

type StoryGraphAudioState = {
  id: string;
  layer?: string;
  phase?: string;
  text?: string;
  speaker?: string;
  audio_file?: string;
};

type StoryGraphMind = {
  id: string;
  entity?: string;
  entity_name?: string;
  phase?: string;
  emotion?: string;
  behavior?: string;
};

type StoryGraphInteraction = {
  between?: string[];
  style?: string;
};

type StoryGraphOutput = {
  stage?: string;
  video_path?: string;
  label?: string;
};

type StoryGraphEventData = {
  id: string;
  description?: string;
  happens_at?: string;
  character_ids?: string[];
  active_appearance_ids?: string[];
  minds?: StoryGraphMind[];
  shots?: StoryGraphShot[];
  interactions?: StoryGraphInteraction[];
  audio_states?: StoryGraphAudioState[];
};

export type StoryGraphViewData = {
  phase?: string;
  production_styles?: StoryGraphProductionStyle[];
  entities?: StoryGraphEntity[];
  timeline?: StoryGraphEventData[];
  parallel_groups?: string[][];
  summary?: Record<string, number>;
  outputs?: StoryGraphOutput[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const useFileUrl = () => {
  const serverBase =
    typeof window !== "undefined" ? window.location.origin : "";
  return (path: string) =>
    path ? `${serverBase}/files/${encodeURIComponent(path)}` : "";
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

// --- Entity Card (with state children) ---

const StateThumb = ({ state }: { state: StoryGraphState }) => {
  const fileUrl = useFileUrl();
  const [imgError, setImgError] = useState(false);
  const imgSrc = state.reference_image ? fileUrl(state.reference_image) : "";
  const tooltip = [state.phase, state.description].filter(Boolean).join(": ");

  return (
    <div className="flex flex-col items-center gap-0.5 shrink-0" title={tooltip}>
      <div className="relative size-9 rounded border border-border/30 bg-muted/20 overflow-hidden flex items-center justify-center">
        {imgSrc && !imgError ? (
          <img
            src={imgSrc}
            alt={state.phase ?? state.id}
            className="size-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="size-full bg-muted/40" />
        )}
      </div>
      {state.phase && (
        <span className="text-[8px] text-muted-foreground/70 text-center leading-tight max-w-[40px] line-clamp-1">
          {state.phase}
        </span>
      )}
    </div>
  );
};

const EntityCard = ({ entity }: { entity: StoryGraphEntity }) => {
  const [imgError, setImgError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fileUrl = useFileUrl();
  const imgSrc = entity.reference_image
    ? fileUrl(entity.reference_image)
    : "";
  const states = entity.states ?? [];
  const hasDetail = Boolean(entity.description) || Boolean(entity.generation_prompt) || states.some((s) => s.description || s.generation_prompt);

  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      {/* Entity image */}
      <button
        type="button"
        className={cn(
          "relative size-12 rounded-md border border-border/40 bg-muted/30 overflow-hidden flex items-center justify-center",
          hasDetail && "cursor-pointer hover:ring-1 hover:ring-primary/40 transition-all",
        )}
        onClick={() => hasDetail && setExpanded(!expanded)}
        disabled={!hasDetail}
      >
        {imgSrc && !imgError ? (
          <img
            src={imgSrc}
            alt={entity.name}
            className="size-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <KindIcon kind={entity.kind} />
        )}
      </button>
      <span className="text-[10px] text-muted-foreground text-center leading-tight line-clamp-2">
        {entity.name}
      </span>
      {/* State children */}
      {states.length > 0 && (
        <div className="flex gap-1 mt-0.5">
          {states.map((s) => (
            <StateThumb key={s.id} state={s} />
          ))}
        </div>
      )}
      {/* Expanded detail panel */}
      {expanded && hasDetail && (
        <div className="w-full min-w-[200px] max-w-[320px] mt-1 rounded-md border border-border/40 bg-card/80 p-2 text-left space-y-2">
          {entity.description && (
            <div className="text-[10px] text-muted-foreground leading-snug">
              {entity.description}
            </div>
          )}
          {entity.generation_prompt && (
            <div className="space-y-0.5">
              <div className="text-[9px] font-medium text-primary/70">Prompt</div>
              <div className="rounded bg-muted/40 px-1.5 py-1 text-[9px] text-foreground/80 leading-snug whitespace-pre-wrap break-words font-mono">
                {entity.generation_prompt}
              </div>
            </div>
          )}
          {states.filter((s) => s.description || s.generation_prompt).map((s) => (
            <div key={s.id} className="space-y-0.5 border-t border-border/20 pt-1.5">
              <div className="text-[9px] font-medium text-foreground/70">
                {s.phase || s.id}
              </div>
              {s.description && (
                <div className="text-[9px] text-muted-foreground/80 leading-snug">
                  {s.description}
                </div>
              )}
              {s.generation_prompt && (
                <div className="space-y-0.5">
                  <div className="text-[9px] font-medium text-primary/70">Prompt</div>
                  <div className="rounded bg-muted/40 px-1.5 py-1 text-[9px] text-foreground/80 leading-snug whitespace-pre-wrap break-words font-mono">
                    {s.generation_prompt}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// --- Production Info Nodes (Style / Ratio / Duration) ---

const ProductionInfoNode = ({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail?: string;
}) => (
  <div className="flex-1 min-w-[120px] rounded-md border border-border/40 bg-muted/20 px-3 py-2">
    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 mb-1">
      {icon}
      <span>{label}</span>
    </div>
    <div className="text-xs font-medium leading-tight">{value || "—"}</div>
    {detail && (
      <div
        className="text-[10px] text-muted-foreground mt-0.5 truncate"
        title={detail}
      >
        {detail}
      </div>
    )}
  </div>
);

// --- Technique Badge ---

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

// --- Shot Asset Thumb ---

const ShotAssetThumb = ({
  src,
  label,
}: {
  src: string;
  label: string;
}) => {
  const [error, setError] = useState(false);
  if (!src || error) return null;
  return (
    <div
      className="relative size-8 rounded border border-border/40 overflow-hidden shrink-0"
      title={label}
    >
      <img
        src={src}
        alt={label}
        className="size-full object-cover"
        onError={() => setError(true)}
      />
      <span className="absolute bottom-0 inset-x-0 bg-black/60 text-[7px] text-white text-center leading-tight">
        {label}
      </span>
    </div>
  );
};

// --- Video Clip Thumb ---

const VideoClipThumb = ({
  src,
  label,
}: {
  src: string;
  label: string;
}) => {
  const [error, setError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  if (!src || error) return null;
  return (
    <div
      className="relative h-8 w-14 rounded border border-border/40 overflow-hidden shrink-0 group cursor-pointer"
      title={label}
      onClick={() => videoRef.current?.paused ? videoRef.current?.play() : videoRef.current?.pause()}
    >
      <video
        ref={videoRef}
        src={src}
        className="size-full object-cover"
        muted
        loop
        preload="metadata"
        onError={() => setError(true)}
      />
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/10 transition-colors">
        <PlayIcon className="size-3 text-white/80" />
      </div>
      <span className="absolute bottom-0 inset-x-0 bg-black/60 text-[7px] text-white text-center leading-tight">
        {label}
      </span>
    </div>
  );
};

// --- Audio Player Inline ---

const AudioInline = ({ src }: { src: string }) => {
  const [error, setError] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);

  if (!src || error) return null;

  const toggle = () => {
    if (!audioRef.current) return;
    if (playing) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setPlaying(!playing);
  };

  return (
    <>
      <audio
        ref={audioRef}
        src={src}
        preload="none"
        onEnded={() => setPlaying(false)}
        onError={() => setError(true)}
      />
      <button
        type="button"
        onClick={toggle}
        className={cn(
          "inline-flex items-center justify-center size-4 rounded-full border border-border/40",
          playing
            ? "bg-primary/20 text-primary"
            : "bg-muted/40 text-muted-foreground hover:bg-muted/60",
        )}
        title={playing ? "Pause" : "Play"}
      >
        <PlayIcon className="size-2" />
      </button>
    </>
  );
};

// --- Audio Layer Icon ---

const AudioLayerIcon = ({ layer }: { layer: string }) => {
  switch (layer) {
    case "audio_bgm":
      return <Music2Icon className="size-3 shrink-0 text-indigo-500/70" />;
    case "audio_ambience":
      return <WavesIcon className="size-3 shrink-0 text-emerald-500/70" />;
    case "audio_dialogue":
      return (
        <MessageCircleIcon className="size-3 shrink-0 text-amber-500/70" />
      );
    default:
      return <Volume2Icon className="size-3 shrink-0 text-muted-foreground" />;
  }
};

// --- Shot Row ---

const ShotRow = ({ shot }: { shot: StoryGraphShot }) => {
  const fileUrl = useFileUrl();
  const refImages = shot.reference_images ?? [];
  const hasAssets =
    refImages.length > 0 ||
    shot.first_frame ||
    shot.tail_frame ||
    shot.video_clip;

  return (
    <div className="py-1 px-2 text-xs space-y-1">
      <div className="flex items-center gap-2">
        <FilmIcon className="size-3 shrink-0 text-muted-foreground" />
        <span className="text-muted-foreground min-w-[2ch]">
          #{shot.order}
        </span>
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
          {shot.techniques?.map((t) => (
            <TechniqueBadge key={t} tech={t} />
          ))}
        </div>
      </div>
      {hasAssets && (
        <div className="flex items-center gap-1.5 ml-5">
          {refImages.map((path) => (
            <ShotAssetThumb
              key={path}
              src={fileUrl(path)}
              label="Ref"
            />
          ))}
          {shot.first_frame && (
            <ShotAssetThumb
              src={fileUrl(shot.first_frame)}
              label="1st"
            />
          )}
          {shot.tail_frame && (
            <ShotAssetThumb
              src={fileUrl(shot.tail_frame)}
              label="Tail"
            />
          )}
          {shot.video_clip && (
            <VideoClipThumb
              src={fileUrl(shot.video_clip)}
              label="Clip"
            />
          )}
        </div>
      )}
    </div>
  );
};

// --- Audio Section (grouped by layer) ---

const AudioChip = ({ audio }: { audio: StoryGraphAudioState }) => {
  const fileUrl = useFileUrl();
  const isDialogue = audio.layer === "audio_dialogue";

  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted/30 px-1.5 py-0.5 text-[9px] text-muted-foreground max-w-[220px]">
      <AudioLayerIcon layer={audio.layer ?? ""} />
      {isDialogue ? (
        <span className="truncate">
          {audio.speaker ? `${audio.speaker}: ` : ""}
          {audio.text ? `\u201C${audio.text}\u201D` : audio.phase}
        </span>
      ) : (
        <span className="truncate">{audio.phase}</span>
      )}
      {audio.audio_file && (
        <AudioInline src={fileUrl(audio.audio_file)} />
      )}
    </span>
  );
};

const AudioSection = ({ audioStates }: { audioStates: StoryGraphAudioState[] }) => {
  if (audioStates.length === 0) return null;

  // Group: BGM + ambience on one line, dialogue on next
  const bgmAndAmb = audioStates.filter(
    (a) => a.layer === "audio_bgm" || a.layer === "audio_ambience",
  );
  const dialogue = audioStates.filter((a) => a.layer === "audio_dialogue");

  return (
    <div className="px-3 py-1.5 space-y-1 border-b border-border/20">
      {bgmAndAmb.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {bgmAndAmb.map((a) => (
            <AudioChip key={a.id} audio={a} />
          ))}
        </div>
      )}
      {dialogue.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {dialogue.map((a) => (
            <AudioChip key={a.id} audio={a} />
          ))}
        </div>
      )}
    </div>
  );
};

// --- Mind Section (per-event character emotions) ---

const MindSection = ({ minds }: { minds: StoryGraphMind[] }) => {
  if (minds.length === 0) return null;

  return (
    <div className="px-3 py-1.5 space-y-1 border-b border-border/20">
      <div className="text-[9px] text-muted-foreground/50 flex items-center gap-1">
        <BrainIcon className="size-2.5" />
        <span>内心状态</span>
      </div>
      {minds.map((mind) => (
        <div
          key={mind.id}
          className="flex items-start gap-1.5 text-[10px] text-muted-foreground"
        >
          <UserIcon className="size-3 shrink-0 mt-0.5 text-purple-500/60" />
          <div className="min-w-0">
            <span className="font-medium text-foreground/80">
              {mind.entity_name || mind.entity}
            </span>
            {mind.phase && (
              <span className="ml-1 text-muted-foreground/70">
                ({mind.phase})
              </span>
            )}
            {mind.emotion && (
              <div className="text-muted-foreground/80 truncate" title={mind.emotion}>
                {mind.emotion}
              </div>
            )}
            {mind.behavior && (
              <div className="text-muted-foreground/60 truncate" title={mind.behavior}>
                {mind.behavior}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

// --- Event Card ---

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
  const interactions = event.interactions ?? [];
  const audioStates = event.audio_states ?? [];
  const activeAppearanceIds = new Set(event.active_appearance_ids ?? []);

  // Build per-event character entities with only active states
  const eventCharacters = (event.character_ids ?? []).map((id) => {
    const entity = entityMap.get(id);
    if (!entity) return null;
    const activeStates = (entity.states ?? []).filter((s) =>
      activeAppearanceIds.has(s.id),
    );
    return { ...entity, states: activeStates };
  }).filter(Boolean) as StoryGraphEntity[];
  const minds = event.minds ?? [];

  const hasDetails = shots.length > 0 || interactions.length > 0 || audioStates.length > 0 || eventCharacters.length > 0 || minds.length > 0;

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
          hasDetails && "cursor-pointer hover:bg-muted/30",
        )}
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
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
            {audioStates.length > 0 && (
              <span className="flex items-center gap-0.5">
                <Volume2Icon className="size-2.5" />
                {audioStates.length}
              </span>
            )}
          </div>
        </div>
        {hasDetails && (
          <div className="flex items-center gap-1 shrink-0 mt-0.5">
            {shots.length > 0 && (
              <span className="text-[10px] text-muted-foreground">
                {shots.length} shot{shots.length > 1 ? "s" : ""}
              </span>
            )}
            <ChevronDownIcon
              className={cn(
                "size-3 text-muted-foreground transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </div>
        )}
      </button>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div className="border-t border-border/40">
          {/* Character appearances active during this event */}
          {eventCharacters.length > 0 && (
            <div className="px-3 py-1.5 border-b border-border/20">
              <div className="flex gap-3 overflow-x-auto pb-1">
                {eventCharacters.map((entity) => (
                  <EntityCard key={entity.id} entity={entity} />
                ))}
              </div>
            </div>
          )}

          {/* Character minds active during this event */}
          <MindSection minds={minds} />

          {/* Interactions */}
          {interactions.length > 0 && (
            <div className="px-3 py-1.5 space-y-0.5 border-b border-border/20">
              {interactions.map((inter, i) => (
                <div
                  key={`inter-${i}`}
                  className="flex items-start gap-1.5 text-[10px] text-muted-foreground"
                >
                  <MessageCircleIcon className="size-3 shrink-0 mt-0.5 text-muted-foreground/50" />
                  <span>{inter.style}</span>
                </div>
              ))}
            </div>
          )}

          {/* Audio states */}
          <AudioSection audioStates={audioStates} />

          {/* Shots */}
          {shots.length > 0 && (
            <div className="divide-y divide-border/20">
              {shots.map((shot) => (
                <ShotRow key={shot.shot_id} shot={shot} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// --- Output Card ---

const OutputCard = ({ output }: { output: StoryGraphOutput }) => {
  const fileUrl = useFileUrl();
  const [error, setError] = useState(false);
  const src = output.video_path ? fileUrl(output.video_path) : "";

  if (!src || error) return null;

  return (
    <div className="flex flex-col items-center gap-1 shrink-0">
      <div className="relative h-16 w-28 rounded-md border border-border/40 bg-muted/30 overflow-hidden">
        <video
          src={src}
          className="size-full object-cover"
          muted
          preload="metadata"
          controls
          onError={() => setError(true)}
        />
      </div>
      <span className="text-[10px] text-muted-foreground text-center leading-tight">
        {output.label || output.stage}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const StoryGraphView = ({ data }: { data: StoryGraphViewData }) => {
  const productionStyles = data.production_styles ?? [];
  const entities = data.entities ?? [];
  const timeline = data.timeline ?? [];
  const parallelGroups = data.parallel_groups ?? [];
  const summary = data.summary ?? {};
  const outputs = data.outputs ?? [];

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

  return (
    <div className="my-2 rounded-md border border-border/50 bg-card/10 overflow-hidden">
      {/* Summary bar */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border/40 bg-muted/20 text-[10px] text-muted-foreground">
        <span className="font-medium text-foreground text-xs">
          Story Graph
        </span>
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
        {summary.audio_states != null && summary.audio_states > 0 && (
          <span>{summary.audio_states} audio</span>
        )}
        {data.phase && (
          <span className="ml-auto rounded bg-muted/60 px-1.5 py-0.5 text-[9px]">
            {data.phase}
          </span>
        )}
      </div>

      {/* Production Info: Style / Ratio / Duration */}
      {productionStyles.length > 0 && (() => {
        const ps = productionStyles[0];
        return (
          <div className="px-3 py-2 border-b border-border/40">
            <div className="flex gap-2">
              <ProductionInfoNode
                icon={<PaletteIcon className="size-3" />}
                label="视频风格"
                value={ps.description || ps.style_prefix || "—"}
                detail={ps.description ? ps.style_prefix : undefined}
              />
              <ProductionInfoNode
                icon={<RatioIcon className="size-3" />}
                label="画面比例"
                value={ps.aspect_ratio || "16:9"}
              />
              <ProductionInfoNode
                icon={<ClockIcon className="size-3" />}
                label="视频时长"
                value={ps.duration || "—"}
              />
            </div>
          </div>
        );
      })()}

      {/* Entity rows */}
      {(characters.length > 0 ||
        locations.length > 0 ||
        props.length > 0) && (
        <div className="px-3 py-2 border-b border-border/40 space-y-2">
          {characters.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Characters
              </div>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {characters.map((e) => (
                  <EntityCard key={e.id} entity={e} />
                ))}
              </div>
            </div>
          )}
          {locations.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Locations
              </div>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {locations.map((e) => (
                  <EntityCard key={e.id} entity={e} />
                ))}
              </div>
            </div>
          )}
          {props.length > 0 && (
            <div>
              <div className="text-[10px] text-muted-foreground/60 mb-1">
                Props
              </div>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {props.map((e) => (
                  <EntityCard key={e.id} entity={e} />
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

      {/* Outputs */}
      {outputs.length > 0 && (
        <div className="px-3 py-2 border-t border-border/40 space-y-1.5">
          <div className="text-[10px] text-muted-foreground/60">
            Outputs ({outputs.length})
          </div>
          <div className="flex gap-3 overflow-x-auto pb-1">
            {outputs.map((o) => (
              <OutputCard key={o.stage} output={o} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
