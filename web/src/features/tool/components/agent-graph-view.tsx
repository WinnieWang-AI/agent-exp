"use client";

import { cn } from "@/lib/utils";
import {
  AlertTriangleIcon,
  BotIcon,
  ChevronDownIcon,
  CircleDotIcon,
  DiamondIcon,
  GitBranchIcon,
  NetworkIcon,
  PlayIcon,
  ShieldCheckIcon,
  SquareIcon,
  UserCheckIcon,
  WrenchIcon,
} from "lucide-react";
import { useState } from "react";

// ---------------------------------------------------------------------------
// Types (matching backend AgentGraphViewDisplayBlock)
// ---------------------------------------------------------------------------

type AgentGraphNode = {
  id: string;
  name: string;
  tools: string[];
  tool_count: number;
  subagent_count: number;
};

type AgentGraphEdge = {
  source: string;
  target: string;
  edge_type: "SUBAGENT" | "CHAT_WITH";
  description: string;
};

type AgentGraphTopology = {
  nodes: AgentGraphNode[];
  edges: AgentGraphEdge[];
};

type WorkflowStep = {
  id: string;
  label: string;
  kind: "begin" | "end" | "task" | "decision" | "user_confirm";
  agent_call?: string | null;
  description?: string;
};

type WorkflowEdge = {
  source: string;
  target: string;
  label?: string;
  is_loop?: boolean;
};

type WorkflowConstraint = {
  id: string;
  rule: string;
  applies_to?: string[];
  check_type?: "keyword" | "parameter" | "count" | "semantic";
};

type AgentWorkflow = {
  agent_id: string;
  steps: WorkflowStep[];
  edges: WorkflowEdge[];
  constraints: WorkflowConstraint[];
  max_loops?: Record<string, number>;
  warnings?: string[];
};

type TraceDeviation = {
  constraint_id?: string;
  rule: string;
  severity: "info" | "warning" | "error";
  expected?: string;
  actual?: string;
  evidence?: string;
};

type TraceCall = {
  seq: number;
  role: "assistant" | "tool" | "user";
  thinking?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: string;
  token_usage?: number;
  deviations?: TraceDeviation[];
};

type StepTrace = {
  step_id: string;
  iteration: number;
  calls: TraceCall[];
  expected_intent?: string;
  applicable_rules?: string[];
  total_tool_calls?: number;
  total_tokens?: number;
};

type StepDeviation = {
  step_id: string;
  deviation_type: "skipped" | "out_of_order" | "loop_exceeded" | "missing" | "unexpected";
  severity: "info" | "warning" | "error";
  description: string;
  expected?: string;
  actual?: string;
};

type DeviationReport = {
  agent_id: string;
  step_deviations?: StepDeviation[];
  summary?: Record<string, number>;
};

export type AgentGraphViewData = {
  type: string;
  topology: AgentGraphTopology;
  workflow?: AgentWorkflow | null;
  deviation_report?: DeviationReport | null;
  traces?: Record<string, StepTrace[]>;
  summary: Record<string, number>;
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const AgentCard = ({
  node,
  edges,
  isRoot,
}: {
  node: AgentGraphNode;
  edges: AgentGraphEdge[];
  isRoot: boolean;
}) => {
  const [expanded, setExpanded] = useState(false);
  const subagentEdges = edges.filter(
    (e) => e.source === node.id && e.edge_type === "SUBAGENT",
  );

  return (
    <div
      className={cn(
        "rounded-md border border-border/50 bg-card/30 overflow-hidden",
        isRoot && "border-blue-500/30",
      )}
    >
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <BotIcon
          className={cn("size-3.5 shrink-0", isRoot ? "text-blue-400" : "text-muted-foreground")}
        />
        <span className="text-xs font-medium text-foreground truncate">
          {node.name}
        </span>
        <span className="ml-auto flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-0.5">
            <WrenchIcon className="size-2.5" />
            {node.tool_count}
          </span>
          {node.subagent_count > 0 && (
            <span className="flex items-center gap-0.5">
              <GitBranchIcon className="size-2.5" />
              {node.subagent_count}
            </span>
          )}
        </span>
        <ChevronDownIcon
          className={cn(
            "size-3 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border/30 px-2.5 py-2 space-y-2">
          {/* Tools */}
          <div>
            <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">
              Tools
            </div>
            <div className="flex flex-wrap gap-1">
              {node.tools.map((tool) => (
                <span
                  key={tool}
                  className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-400"
                >
                  {tool}
                </span>
              ))}
            </div>
          </div>

          {/* Subagents */}
          {subagentEdges.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1">
                Subagents
              </div>
              <div className="space-y-1">
                {subagentEdges.map((edge) => (
                  <div
                    key={edge.target}
                    className="rounded bg-blue-500/10 px-2 py-1"
                  >
                    <span className="text-[10px] font-medium text-blue-400">
                      {edge.target}
                    </span>
                    {edge.description && (
                      <p className="text-[9px] text-muted-foreground mt-0.5 line-clamp-2">
                        {edge.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Workflow step icon
// ---------------------------------------------------------------------------

const StepKindIcon = ({ kind }: { kind: WorkflowStep["kind"] }) => {
  switch (kind) {
    case "begin":
      return <PlayIcon className="size-3 text-green-400" />;
    case "end":
      return <CircleDotIcon className="size-3 text-red-400" />;
    case "task":
      return <SquareIcon className="size-3 text-amber-400" />;
    case "decision":
      return <DiamondIcon className="size-3 text-purple-400" />;
    case "user_confirm":
      return <UserCheckIcon className="size-3 text-pink-400" />;
    default:
      return <SquareIcon className="size-3 text-muted-foreground" />;
  }
};

const kindColor: Record<string, string> = {
  begin: "text-green-400",
  end: "text-red-400",
  task: "text-amber-400",
  decision: "text-purple-400",
  user_confirm: "text-pink-400",
};

// ---------------------------------------------------------------------------
// Workflow step row
// ---------------------------------------------------------------------------

const WorkflowStepRow = ({
  step,
  outEdges,
}: {
  step: WorkflowStep;
  outEdges: WorkflowEdge[];
}) => {
  const [expanded, setExpanded] = useState(false);
  const loopEdges = outEdges.filter((e) => e.is_loop);

  return (
    <div className="rounded border border-border/30 overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-muted/20 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <StepKindIcon kind={step.kind} />
        <span className={cn("text-[11px] font-medium", kindColor[step.kind] ?? "text-foreground")}>
          {step.label}
        </span>
        {step.agent_call && (
          <span className="rounded bg-blue-500/15 px-1 py-0.5 text-[9px] text-blue-400">
            {step.agent_call}
          </span>
        )}
        {loopEdges.length > 0 && (
          <span className="text-[9px] text-red-400/70">&#8635;</span>
        )}
        <ChevronDownIcon
          className={cn(
            "ml-auto size-3 shrink-0 text-muted-foreground transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>
      {expanded && (
        <div className="border-t border-border/20 px-2.5 py-1.5 text-[10px] text-muted-foreground space-y-1">
          {step.description && <p>{step.description}</p>}
          <div className="text-[9px]">
            <span className="text-muted-foreground/60">kind: </span>
            <span>{step.kind}</span>
            {step.agent_call && (
              <>
                <span className="text-muted-foreground/60"> | calls: </span>
                <span className="text-blue-400">{step.agent_call}</span>
              </>
            )}
          </div>
          {outEdges.length > 0 && (
            <div className="space-y-0.5">
              {outEdges.map((e, i) => (
                <div key={i} className="flex items-center gap-1 text-[9px]">
                  <span className="text-muted-foreground/60">&rarr;</span>
                  <span>{e.target}</span>
                  {e.label && (
                    <span className="rounded bg-muted/40 px-1 py-0.5">{e.label}</span>
                  )}
                  {e.is_loop && (
                    <span className="text-red-400/70">(loop)</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Constraint badge
// ---------------------------------------------------------------------------

const checkTypeStyle: Record<string, string> = {
  keyword: "bg-emerald-500/10 text-emerald-400",
  parameter: "bg-blue-500/10 text-blue-400",
  count: "bg-amber-500/10 text-amber-400",
  semantic: "bg-purple-500/10 text-purple-400",
};

const severityStyle: Record<string, string> = {
  error: "border-red-500/40 bg-red-500/5",
  warning: "border-amber-500/40 bg-amber-500/5",
  info: "border-blue-500/40 bg-blue-500/5",
};

const severityText: Record<string, string> = {
  error: "text-red-400",
  warning: "text-amber-400",
  info: "text-blue-400",
};

// ---------------------------------------------------------------------------
// Trace viewer
// ---------------------------------------------------------------------------

const TraceCallRow = ({ call }: { call: TraceCall }) => {
  const hasDeviations = call.deviations && call.deviations.length > 0;
  return (
    <div
      className={cn(
        "rounded border px-2 py-1 text-[10px]",
        hasDeviations ? "border-red-500/30 bg-red-500/5" : "border-border/20",
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground/60 text-[9px] w-4">
          #{call.seq}
        </span>
        <span
          className={cn(
            "font-medium",
            call.role === "assistant" ? "text-blue-400" : "text-emerald-400",
          )}
        >
          {call.role}
        </span>
        {call.tool_name && (
          <span className="text-muted-foreground">
            {call.tool_name}
            {call.tool_args?.subagent_name
              ? ` → ${call.tool_args.subagent_name as string}`
              : ""}
          </span>
        )}
        {call.token_usage != null && call.token_usage > 0 && (
          <span className="ml-auto text-[9px] text-muted-foreground/50">
            {call.token_usage.toLocaleString()} tok
          </span>
        )}
      </div>
      {call.tool_args?.prompt && (
        <div className="mt-0.5 text-[9px] text-muted-foreground/70 line-clamp-2">
          {String(call.tool_args.prompt)}
        </div>
      )}
      {call.tool_result && (
        <div className="mt-0.5 text-[9px] text-muted-foreground/50 line-clamp-2">
          {call.tool_result}
        </div>
      )}
      {hasDeviations &&
        call.deviations!.map((dev, i) => (
          <div
            key={i}
            className={cn(
              "mt-1 rounded border px-1.5 py-1",
              severityStyle[dev.severity],
            )}
          >
            <div className="flex items-center gap-1">
              <AlertTriangleIcon
                className={cn("size-2.5", severityText[dev.severity])}
              />
              <span className={cn("text-[9px] font-medium", severityText[dev.severity])}>
                {dev.severity.toUpperCase()}
              </span>
              <span className="text-[9px] text-muted-foreground">
                {dev.rule}
              </span>
            </div>
            {dev.evidence && (
              <div className="text-[9px] text-muted-foreground/60 mt-0.5">
                {dev.evidence}
              </div>
            )}
          </div>
        ))}
    </div>
  );
};

const StepTraceView = ({
  traces,
  stepLabel,
}: {
  traces: StepTrace[];
  stepLabel: string;
}) => {
  const [selectedIter, setSelectedIter] = useState(0);
  if (traces.length === 0) return null;
  const trace = traces[selectedIter];
  if (!trace) return null;

  const totalDevs = trace.calls.reduce(
    (acc, c) => acc + (c.deviations?.length ?? 0),
    0,
  );

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-[10px]">
        <span className="text-muted-foreground">{stepLabel}</span>
        {trace.expected_intent && (
          <span className="text-[9px] text-muted-foreground/50 truncate">
            — {trace.expected_intent}
          </span>
        )}
      </div>
      {/* Iteration tabs */}
      {traces.length > 1 && (
        <div className="flex gap-0.5">
          {traces.map((t, i) => {
            const iterDevs = t.calls.reduce(
              (acc, c) => acc + (c.deviations?.length ?? 0),
              0,
            );
            return (
              <button
                key={i}
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5 text-[9px] transition-colors",
                  i === selectedIter
                    ? "bg-foreground/10 text-foreground"
                    : "text-muted-foreground hover:bg-muted/30",
                  iterDevs > 0 && "text-red-400",
                )}
                onClick={() => setSelectedIter(i)}
              >
                #{t.iteration}
                {iterDevs > 0 && "!"}
              </button>
            );
          })}
        </div>
      )}
      {/* Trace calls */}
      <div className="space-y-0.5">
        {trace.calls.map((call) => (
          <TraceCallRow key={call.seq} call={call} />
        ))}
      </div>
      {/* Stats */}
      <div className="text-[9px] text-muted-foreground/50 flex gap-3">
        <span>{trace.total_tool_calls ?? 0} calls</span>
        <span>{(trace.total_tokens ?? 0).toLocaleString()} tokens</span>
        {totalDevs > 0 && (
          <span className="text-red-400">{totalDevs} deviation(s)</span>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const AgentGraphView = ({ data }: { data: AgentGraphViewData }) => {
  const topology = data.topology ?? { nodes: [], edges: [] };
  const workflow = data.workflow;
  const summary = data.summary ?? {};
  const nodes = topology.nodes ?? [];
  const edges = topology.edges ?? [];

  // Identify root agents (not a subagent target)
  const targetIds = new Set(
    edges.filter((e) => e.edge_type === "SUBAGENT").map((e) => e.target),
  );
  const rootNodes = nodes.filter((n) => !targetIds.has(n.id));
  const subNodes = nodes.filter((n) => targetIds.has(n.id));

  // Build tree structure for rendering
  const buildTree = (nodeId: string, depth: number): React.ReactNode => {
    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;
    const childEdges = edges.filter(
      (e) => e.source === nodeId && e.edge_type === "SUBAGENT",
    );
    return (
      <div key={nodeId} className={cn(depth > 0 && "ml-4 mt-1")}>
        <AgentCard node={node} edges={edges} isRoot={depth === 0} />
        {childEdges.map((e) => buildTree(e.target, depth + 1))}
      </div>
    );
  };

  // Workflow edge lookup
  const wfEdgesBySource: Record<string, WorkflowEdge[]> = {};
  if (workflow) {
    for (const e of workflow.edges) {
      (wfEdgesBySource[e.source] ??= []).push(e);
    }
  }

  return (
    <div className="my-2 rounded-md border border-border/50 bg-card/10 overflow-hidden">
      {/* Summary bar */}
      <div className="flex items-center gap-3 px-3 py-1.5 border-b border-border/40 bg-muted/20 text-[10px] text-muted-foreground">
        <span className="font-medium text-foreground text-xs flex items-center gap-1.5">
          <NetworkIcon className="size-3.5" />
          Agent Graph
        </span>
        {summary.agents != null && <span>{summary.agents} agents</span>}
        {summary.edges != null && <span>{summary.edges} edges</span>}
        {summary.total_tools != null && (
          <span>{summary.total_tools} tools</span>
        )}
        {summary.workflow_steps != null && (
          <span>{summary.workflow_steps} steps</span>
        )}
        {(summary.loops as number) > 0 && (
          <span>{summary.loops} loops</span>
        )}
      </div>

      {/* Agent topology */}
      <div className="px-3 py-2 space-y-1">
        <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
          <BotIcon className="size-3" />
          Topology
        </div>
        {rootNodes.map((root) => buildTree(root.id, 0))}
        {subNodes
          .filter(
            (n) => !rootNodes.some((r) => {
              const descendants = new Set<string>();
              const collect = (id: string) => {
                descendants.add(id);
                edges
                  .filter((e) => e.source === id && e.edge_type === "SUBAGENT")
                  .forEach((e) => collect(e.target));
              };
              collect(r.id);
              return descendants.has(n.id);
            }),
          )
          .map((n) => (
            <AgentCard key={n.id} node={n} edges={edges} isRoot={false} />
          ))}
      </div>

      {/* Workflow */}
      {workflow && workflow.steps.length > 0 && (
        <div className="px-3 py-2 border-t border-border/40 space-y-1">
          <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
            <GitBranchIcon className="size-3" />
            Workflow: {workflow.agent_id}
          </div>
          <div className="space-y-0.5">
            {workflow.steps.map((step) => (
              <WorkflowStepRow
                key={step.id}
                step={step}
                outEdges={wfEdgesBySource[step.id] ?? []}
              />
            ))}
          </div>
        </div>
      )}

      {/* Constraints */}
      {workflow && workflow.constraints.length > 0 && (
        <div className="px-3 py-2 border-t border-border/40 space-y-1">
          <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
            <ShieldCheckIcon className="size-3" />
            Constraints ({workflow.constraints.length})
          </div>
          <div className="space-y-0.5">
            {workflow.constraints.map((c) => (
              <div
                key={c.id}
                className="flex items-start gap-1.5 rounded border border-border/20 px-2 py-1"
              >
                <span
                  className={cn(
                    "shrink-0 rounded px-1 py-0.5 text-[9px] font-medium",
                    checkTypeStyle[c.check_type ?? "semantic"],
                  )}
                >
                  {c.check_type ?? "semantic"}
                </span>
                <span className="text-[10px] text-foreground/80">
                  {c.rule}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {workflow && workflow.warnings && workflow.warnings.length > 0 && (
        <div className="px-3 py-2 border-t border-border/40">
          <div className="space-y-0.5">
            {workflow.warnings.map((w, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 text-[10px] text-amber-400/80"
              >
                <AlertTriangleIcon className="size-3 shrink-0" />
                {w}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Deviation Report */}
      {data.deviation_report &&
        data.deviation_report.step_deviations &&
        data.deviation_report.step_deviations.length > 0 && (
          <div className="px-3 py-2 border-t border-border/40 space-y-1">
            <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
              <AlertTriangleIcon className="size-3" />
              Deviations
              {data.deviation_report.summary && (
                <span className="ml-1 text-[9px] normal-case tracking-normal">
                  ({Object.entries(data.deviation_report.summary)
                    .filter(([, v]) => v > 0)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(", ")})
                </span>
              )}
            </div>
            <div className="space-y-0.5">
              {data.deviation_report.step_deviations.map((dev, i) => (
                <div
                  key={i}
                  className={cn(
                    "rounded border px-2 py-1 text-[10px]",
                    severityStyle[dev.severity],
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <AlertTriangleIcon
                      className={cn("size-2.5 shrink-0", severityText[dev.severity])}
                    />
                    <span className={cn("font-medium text-[9px]", severityText[dev.severity])}>
                      {dev.severity.toUpperCase()}
                    </span>
                    <span className="rounded bg-muted/30 px-1 py-0.5 text-[9px] text-muted-foreground">
                      {dev.deviation_type}
                    </span>
                    <span className="text-muted-foreground text-[9px]">
                      {dev.step_id}
                    </span>
                  </div>
                  <div className="mt-0.5 text-foreground/70">
                    {dev.description}
                  </div>
                  {dev.expected && (
                    <div className="text-[9px] text-muted-foreground/60 mt-0.5">
                      expected: {dev.expected} | actual: {dev.actual}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      {/* Step Traces */}
      {data.traces && Object.keys(data.traces).length > 0 && (
        <div className="px-3 py-2 border-t border-border/40 space-y-2">
          <div className="text-[9px] uppercase tracking-wider text-muted-foreground mb-1 flex items-center gap-1">
            <PlayIcon className="size-3" />
            Execution Traces
          </div>
          {Object.entries(data.traces).map(([stepId, stepTraces]) => {
            const stepDef = workflow?.steps.find((s) => s.id === stepId);
            return (
              <StepTraceView
                key={stepId}
                traces={stepTraces}
                stepLabel={stepDef?.label ?? stepId}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};
