"use client";

import {
  addEdge,
  Background,
  Controls,
  type Connection,
  type Edge,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useMemo, useState } from "react";
import { useUnsavedChangesWarning } from "@/lib/use-unsaved-changes";

type DiagramConfig = {
  starter_nodes?: Array<{
    id?: string;
    label?: string;
    type?: string;
    position?: { x: number; y: number };
  }>;
  starter_edges?: Array<{
    id?: string;
    source: string;
    target: string;
    label?: string;
  }>;
  palette?: Array<{ type: string; label: string }>;
};

type Saved =
  | {
      nodes: Array<{
        id: string;
        type?: string;
        label?: string;
        position?: { x: number; y: number };
      }>;
      edges: Array<{
        id: string;
        source: string;
        target: string;
        label?: string;
      }>;
    }
  | undefined;

const FALLBACK_PALETTE = [
  { type: "default", label: "Step" },
  { type: "input", label: "Trigger" },
  { type: "output", label: "Outcome" },
  { type: "default", label: "Decision" },
];

let nextId = 1;
const newNodeId = (): string => `n${Date.now().toString(36)}-${nextId++}`;

function bootstrapNodes(config: DiagramConfig, saved: Saved): Node[] {
  const source = saved?.nodes?.length
    ? saved.nodes
    : config.starter_nodes ?? [];
  return source.map((n, i) => ({
    id: n.id ?? newNodeId(),
    type: n.type ?? "default",
    data: { label: n.label ?? `Node ${i + 1}` },
    position: n.position ?? { x: 100 + i * 180, y: 100 + (i % 2) * 100 },
  }));
}

function bootstrapEdges(config: DiagramConfig, saved: Saved): Edge[] {
  const source = saved?.edges?.length
    ? saved.edges
    : config.starter_edges ?? [];
  return source.map((e) => ({
    id: e.id ?? `e-${e.source}-${e.target}-${newNodeId()}`,
    source: e.source,
    target: e.target,
    label: e.label,
  }));
}

export function DiagramRenderer({
  config,
  initialAnswer,
}: {
  config: DiagramConfig;
  initialAnswer: Saved;
}) {
  return (
    <ReactFlowProvider>
      <DiagramCanvas config={config} initialAnswer={initialAnswer} />
    </ReactFlowProvider>
  );
}

function DiagramCanvas({
  config,
  initialAnswer,
}: {
  config: DiagramConfig;
  initialAnswer: Saved;
}) {
  const initialNodes = useMemo(() => bootstrapNodes(config, initialAnswer), [config, initialAnswer]);
  const initialEdges = useMemo(() => bootstrapEdges(config, initialAnswer), [config, initialAnswer]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initialEdges);
  const [renaming, setRenaming] = useState<{ id: string; label: string } | null>(
    null
  );

  useUnsavedChangesWarning(
    JSON.stringify({ nodes, edges }) !==
      JSON.stringify({ nodes: initialNodes, edges: initialEdges })
  );

  const palette = config.palette?.length ? config.palette : FALLBACK_PALETTE;

  const onConnect = useCallback(
    (conn: Connection) =>
      setEdges((current) =>
        addEdge({ ...conn, id: `e-${conn.source}-${conn.target}-${Date.now()}` }, current)
      ),
    [setEdges]
  );

  const addNode = useCallback(
    (item: { type: string; label: string }) => {
      setNodes((current) => [
        ...current,
        {
          id: newNodeId(),
          type: item.type === "input" || item.type === "output" ? item.type : "default",
          data: { label: item.label },
          position: {
            x: 60 + ((current.length * 60) % 360),
            y: 60 + ((current.length * 60) % 240),
          },
        },
      ]);
    },
    [setNodes]
  );

  const onNodeDoubleClick = useCallback((_evt: unknown, node: Node) => {
    const label = (node.data as { label?: string })?.label ?? "";
    setRenaming({ id: node.id, label });
  }, []);

  const commitRename = useCallback(() => {
    if (!renaming) return;
    setNodes((current) =>
      current.map((n) =>
        n.id === renaming.id
          ? { ...n, data: { ...n.data, label: renaming.label } }
          : n
      )
    );
    setRenaming(null);
  }, [renaming, setNodes]);

  // Serialize for the form action: strips React Flow internals so the
  // server only sees structural data.
  const serialized = {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      label: (n.data as { label?: string })?.label ?? "",
      position: n.position,
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: typeof e.label === "string" ? e.label : "",
    })),
  };

  return (
    <div className="space-y-2">
      <input
        name="answer"
        type="hidden"
        value={JSON.stringify({ diagram: serialized })}
      />
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="text-muted-foreground">Add:</span>
        {palette.map((item) => (
          <button
            className="rounded border border-border bg-card px-2 py-1 hover:bg-primary/10"
            key={`${item.type}-${item.label}`}
            onClick={() => addNode(item)}
            type="button"
          >
            {item.label}
          </button>
        ))}
        <span className="ml-auto text-muted-foreground">
          Drag to position · double-click to rename · drag from a node edge to connect
        </span>
      </div>

      <div
        className="h-[420px] overflow-hidden rounded border border-border bg-card"
        data-allow-paste="true"
      >
        <ReactFlow
          edges={edges}
          fitView
          nodes={nodes}
          onConnect={onConnect}
          onEdgesChange={onEdgesChange}
          onNodeDoubleClick={onNodeDoubleClick}
          onNodesChange={onNodesChange}
        >
          <Background gap={16} />
          <Controls />
        </ReactFlow>
      </div>

      {renaming && (
        <div className="flex items-center gap-2 rounded border border-border bg-card p-2 text-xs">
          <span className="text-muted-foreground">Rename node:</span>
          <input
            autoFocus
            className="flex-1 rounded border border-border bg-background px-2 py-1"
            onChange={(e) =>
              setRenaming({ id: renaming.id, label: e.target.value })
            }
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setRenaming(null);
            }}
            value={renaming.label}
          />
          <button
            className="rounded bg-primary px-2 py-1 text-primary-foreground font-medium"
            onClick={commitRename}
            type="button"
          >
            Save
          </button>
        </div>
      )}
    </div>
  );
}
