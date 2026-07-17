// Client API Noreon — centralise les appels au backend FastAPI.
// Le tenant est passé via l'en-tête X-Tenant (isolation multi-entreprise).

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const TENANT = "demo";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Tenant": TENANT,
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Types ----
export interface Connection {
  id: number;
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  status: string;
  is_read_only: boolean | null;
  read_only_detail: string | null;
  last_error: string | null;
  last_scanned_at: string | null;
}

export interface Probe {
  connection_ok: boolean;
  server_version: string | null;
  read_only: boolean | null;
  read_only_detail: string | null;
  error: string | null;
}

export interface CreateResult {
  connection: Connection;
  probe: Probe;
  read_only_alert: string | null;
}

export interface Column {
  name: string;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
}
export interface Table {
  id: number;
  schema_name: string;
  table_name: string;
  table_type: string;
  estimated_rows: number | null;
  columns: Column[];
}
export interface Relation {
  id: number;
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  kind: string;
  status: string;
  confidence: number;
  cardinality: string | null;
  integrity_ratio: number | null;
}

export interface GraphNode {
  table: string;
  name: string;
  entity: string | null;
  concepts: string[];
  rows: number | null;
  columns: number;
  quality: number | null;
  table_type: string;
}
export interface GraphEdge {
  id: number;
  from: string;
  to: string;
  from_column: string;
  to_column: string;
  kind: string;
  status: string;
  confidence: number;
  cardinality: string | null;
  integrity_ratio: number | null;
}
export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
export interface Profile {
  schema_name: string;
  table_name: string;
  column_name: string;
  declared_type: string | null;
  detected_type: string | null;
  pii_type: string | null;
  sampled: boolean;
  null_rate: number | null;
  distinct_count: number | null;
  min_value: string | null;
  max_value: string | null;
  top_values: { value: any; count: number }[];
}
export interface QualityDimension {
  name: string;
  applicable: boolean;
  score: number | null;
  weight: number;
  detail: string;
}
export interface QualityScore {
  level: string;
  schema_name: string | null;
  table_name: string | null;
  column_name: string | null;
  relation_ref: string | null;
  score: number;
  detail: string;
  dimensions: QualityDimension[];
}

export interface ConceptMapping {
  id: number;
  concept_name: string;
  concept_description: string;
  schema_name: string;
  table_name: string;
  column_name: string;
  confidence: number;
  rationale: string;
  status: string;
  needs_arbitration: boolean;
  arbitration_note: string | null;
  review_note: string | null;
  reviewed_at: string | null;
}

export interface ChatResponse {
  status: string;
  question: string;
  message: string;
  sql: string | null;
  tables_used: string[];
  columns_used: string[];
  assumptions: string[];
  rationale: string;
  columns: string[];
  rows: any[][];
  row_count: number;
  duration_ms: number | null;
  estimated_cost: number | null;
  truncated: boolean;
  warnings: string[];
  analysis: any | null;
  confidence: { percent: number; factors: string[] } | null;
  table_quality: Record<string, number>;
  chart: {
    type: string;
    x: string | null;
    y: string[];
    reason: string;
    alternatives: string[];
  } | null;
  privacy: {
    engine: string;
    method: string;
    protected_columns: Record<string, string>;
    values_protected: number;
  } | null;
}

// ---- Endpoints ----
export const api = {
  listConnections: () => request<Connection[]>("/connections"),
  getConnection: (id: number) => request<Connection>(`/connections/${id}`),
  createConnection: (payload: any) =>
    request<CreateResult>("/connections", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  testConnection: (id: number) =>
    request<Probe>(`/connections/${id}/test`, { method: "POST" }),
  deleteConnection: (id: number) =>
    request<void>(`/connections/${id}`, { method: "DELETE" }),
  scan: (id: number) => request<any>(`/connections/${id}/scan`, { method: "POST" }),
  schema: (id: number) => request<Table[]>(`/connections/${id}/schema`),
  relations: (id: number) => request<Relation[]>(`/connections/${id}/relations`),
  graph: (id: number) => request<Graph>(`/connections/${id}/graph`),
  relationReview: (id: number, relationId: number, action: "validate" | "reject") =>
    request<Relation>(`/connections/${id}/relations/${relationId}/review`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  profile: (id: number) =>
    request<any>(`/connections/${id}/profile`, { method: "POST" }),
  jobs: (id: number) => request<any[]>(`/connections/${id}/profile/jobs`),
  profiles: (id: number, table?: string) =>
    request<Profile[]>(
      `/connections/${id}/profiles${table ? `?table=${encodeURIComponent(table)}` : ""}`,
    ),
  semanticPropose: (id: number) =>
    request<any>(`/connections/${id}/semantic/propose`, { method: "POST" }),
  semanticList: (id: number) =>
    request<ConceptMapping[]>(`/connections/${id}/semantic`),
  semanticReview: (
    id: number,
    mappingId: number,
    action: "validate" | "reject" | "correct",
    conceptName?: string,
  ) =>
    request<ConceptMapping>(`/connections/${id}/semantic/${mappingId}/review`, {
      method: "POST",
      body: JSON.stringify({ action, concept_name: conceptName ?? null }),
    }),
  semanticExportUrl: (id: number, format: "csv" | "json") =>
    `${API_BASE}/connections/${id}/semantic/export?format=${format}`,
  runQuality: (id: number) =>
    request<any>(`/connections/${id}/quality`, { method: "POST" }),
  quality: (id: number, level?: string) =>
    request<QualityScore[]>(
      `/connections/${id}/quality${level ? `?level=${level}` : ""}`,
    ),
  chat: (id: number, question: string) =>
    request<ChatResponse>(`/connections/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),
  queries: (id: number) => request<any[]>(`/connections/${id}/queries`),
};
