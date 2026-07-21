// Client API Noreon — centralise les appels au backend FastAPI.
// Authentification (Module 11) : si un jeton est présent, on envoie
// `Authorization: Bearer`. Sinon, en dev, on retombe sur l'en-tête X-Tenant
// (admin implicite du tenant démo).

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const TENANT = "demo";
const TOKEN_KEY = "noreon_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : { "X-Tenant": TENANT };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      clearToken();
    }
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
  engine: string;
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

export interface BusinessDefinition {
  id: number;
  name: string;
  kind: string;
  schema_name: string;
  table_name: string;
  expression: string | null;
  filter_sql: string | null;
  description: string;
  source_question: string | null;
}

export interface Alert {
  id: number;
  name: string;
  description: string;
  definition_id: number | null;
  schema_name: string;
  table_name: string | null;
  expression: string | null;
  filter_sql: string | null;
  comparison: string;
  threshold: number;
  last_value: number | null;
  previous_value: number | null;
  last_status: string;
  last_message: string | null;
  last_checked_at: string | null;
}

export interface AlertEvent {
  id: number;
  value: number | null;
  status: string;
  message: string;
  created_at: string;
}

export interface Preferences {
  preferred_chart_type: string | null;
  auto_learn: boolean;
  auto_save_definitions: boolean;
}

export interface TokenResp {
  access_token: string;
  token_type: string;
  role: string;
  email: string;
  mfa_required: boolean;
}
export interface Me {
  user_id: number | null;
  email: string | null;
  role: string;
  tenant_id: number;
}
export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  mfa_enabled: boolean;
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
  investigation: {
    question: string;
    subject: string;
    metric_label: string;
    plan: { title: string; rationale: string }[];
    steps: { title: string; question: string; rationale: string; sql: string; finding: string; figures: any[] }[];
    key_drivers: string[];
    conclusion: string;
    recommendations: string[];
    queries: string[];
    trend_columns: string[];
    trend_rows: any[][];
  } | null;
  deep: {
    subject: string;
    metric_label: string;
    context: string[];
    segments: {
      dimension: string;
      kind: string;
      metric: string;
      n_groups: number;
      groups: { segment: string; value: number; share: number; count: number; avg?: number }[];
    }[];
    drivers: string[];
    crosstab: {
      dim_a: string;
      dim_b: string;
      metric: string;
      cells: { a: string; b: string; value: number; count: number }[];
    } | null;
    findings: string[];
    recommendations: string[];
    queries: string[];
  } | null;
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

// ---- Conversations (historique serveur, dossiers, archivage) ----
export interface ConvFolder {
  id: number;
  name: string;
  created_at: string | null;
}
export interface ConvTurn {
  id: number;
  ordinal: number;
  question: string;
  deep: boolean;
  connection_id?: number | null;
  response: ChatResponse | null;
  error: string | null;
  created_at: string | null;
}
export interface ConvSummary {
  id: number;
  title: string;
  folder_id: number | null;
  archived: boolean;
  turn_count: number;
  created_at: string | null;
  updated_at: string | null;
}
export interface ConvFull extends ConvSummary {
  turns: ConvTurn[];
}

// ---- Espaces & gouvernance ----
export interface Space {
  id: number;
  name: string;
  slug: string;
  description: string;
  connection_ids: number[];
  created_at: string | null;
}
export interface SpaceDetail extends Space {
  connections: { id: number; name: string; engine: string; is_read_only: boolean | null }[];
  members: { user_id: number; email: string; role: string }[];
}
export interface GovColumn {
  name: string;
  data_type: string;
  enabled: boolean;
}
export interface GovTable {
  schema: string;
  table: string;
  enabled: boolean;
  columns: GovColumn[];
}
export interface Governance {
  scanned: boolean;
  tables: GovTable[];
}

// ---- Rapports ----
export interface ReportBlock {
  id: number;
  ordinal: number;
  kind: "markdown" | "table" | "chart";
  content: any;
}
export interface ReportSummary {
  id: number;
  title: string;
  space_id: number | null;
  block_count: number;
  created_at: string | null;
  updated_at: string | null;
}
export interface ReportFull extends ReportSummary {
  blocks: ReportBlock[];
}

// ---- Découvertes (suggestions automatiques) ----
export interface DiscoveryItem {
  category: "anomaly" | "trend" | "suspicious_column" | "incoherent_relation";
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  table: string | null;
  column: string | null;
  suggested_question: string | null;
}
export interface Discoveries {
  scanned: boolean;
  counts: {
    anomalies: number;
    trends: number;
    suspicious_columns: number;
    incoherent_relations: number;
  };
  items: DiscoveryItem[];
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
  uploadFileConnection: async (name: string, file: File): Promise<CreateResult> => {
    const form = new FormData();
    form.append("name", name);
    form.append("file", file);
    const res = await fetch(`${API_BASE}/connections/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail;
      } catch {}
      throw new Error(detail);
    }
    return res.json();
  },
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
  chat: (id: number, question: string, deep = true) =>
    request<ChatResponse>(`/connections/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ question, deep_analysis: deep }),
    }),
  queries: (id: number) => request<any[]>(`/connections/${id}/queries`),
  discoveries: (id: number) => request<Discoveries>(`/connections/${id}/discoveries`),

  // --- Conversations serveur ---
  convList: (id: number, archived = false) =>
    request<ConvSummary[]>(`/connections/${id}/conversations?archived=${archived}`),
  convGet: (id: number, cid: number) =>
    request<ConvFull>(`/connections/${id}/conversations/${cid}`),
  convCreate: (id: number, body: { title?: string; folder_id?: number | null }) =>
    request<ConvFull>(`/connections/${id}/conversations`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  convUpdate: (
    id: number,
    cid: number,
    patch: { title?: string; folder_id?: number | null; archived?: boolean },
  ) =>
    request<ConvSummary>(`/connections/${id}/conversations/${cid}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  convDelete: (id: number, cid: number) =>
    request<any>(`/connections/${id}/conversations/${cid}`, { method: "DELETE" }),
  convAddTurn: (id: number, cid: number, question: string, deep: boolean) =>
    request<{ turn: ConvTurn; conversation: ConvSummary }>(
      `/connections/${id}/conversations/${cid}/turns`,
      { method: "POST", body: JSON.stringify({ question, deep_analysis: deep }) },
    ),
  folderList: (id: number) =>
    request<ConvFolder[]>(`/connections/${id}/conversations/folders`),
  folderCreate: (id: number, name: string) =>
    request<ConvFolder>(`/connections/${id}/conversations/folders`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  folderDelete: (id: number, fid: number) =>
    request<any>(`/connections/${id}/conversations/folders/${fid}`, {
      method: "DELETE",
    }),

  // --- Authentification & rôles (Module 11) ---
  register: (tenant_slug: string, email: string, password: string, full_name = "") =>
    request<TokenResp>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ tenant_slug, email, password, full_name }),
    }),
  login: (tenant_slug: string, email: string, password: string, mfa_code?: string) =>
    request<TokenResp>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ tenant_slug, email, password, mfa_code: mfa_code ?? null }),
    }),
  me: () => request<Me>("/auth/me"),

  // --- Espaces & gouvernance ---
  spaces: () => request<Space[]>("/spaces"),
  spaceCreate: (name: string, description = "") =>
    request<Space>("/spaces", { method: "POST", body: JSON.stringify({ name, description }) }),
  space: (sid: number) => request<SpaceDetail>(`/spaces/${sid}`),
  spaceDelete: (sid: number) => request<any>(`/spaces/${sid}`, { method: "DELETE" }),
  spaceAttach: (sid: number, connection_id: number) =>
    request<SpaceDetail>(`/spaces/${sid}/connections`, {
      method: "POST",
      body: JSON.stringify({ connection_id }),
    }),
  spaceDetach: (sid: number, cid: number) =>
    request<SpaceDetail>(`/spaces/${sid}/connections/${cid}`, { method: "DELETE" }),
  spaceAddMember: (sid: number, user_id: number, role = "member") =>
    request<SpaceDetail>(`/spaces/${sid}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id, role }),
    }),
  spaceRemoveMember: (sid: number, uid: number) =>
    request<SpaceDetail>(`/spaces/${sid}/members/${uid}`, { method: "DELETE" }),
  governance: (sid: number, cid: number) =>
    request<Governance>(`/spaces/${sid}/connections/${cid}/governance`),
  toggleTable: (sid: number, cid: number, schema: string, table: string, enabled: boolean) =>
    request<any>(`/spaces/${sid}/connections/${cid}/tables/${schema}/${table}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  toggleColumn: (
    sid: number, cid: number, schema: string, table: string, column: string, enabled: boolean,
  ) =>
    request<any>(`/spaces/${sid}/connections/${cid}/columns/${schema}/${table}/${column}`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  spaceChat: (sid: number, connection_id: number, question: string, deep: boolean) =>
    request<ChatResponse>(`/spaces/${sid}/chat`, {
      method: "POST",
      body: JSON.stringify({ connection_id, question, deep_analysis: deep }),
    }),

  // --- Rapports ---
  reports: (spaceId?: number) =>
    request<ReportSummary[]>(`/reports${spaceId != null ? `?space_id=${spaceId}` : ""}`),
  reportCreate: (title?: string, space_id?: number | null) =>
    request<ReportFull>("/reports", { method: "POST", body: JSON.stringify({ title, space_id }) }),
  report: (rid: number) => request<ReportFull>(`/reports/${rid}`),
  reportRename: (rid: number, title: string) =>
    request<ReportSummary>(`/reports/${rid}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  reportDelete: (rid: number) => request<any>(`/reports/${rid}`, { method: "DELETE" }),
  reportGenerate: (rid: number, prompt: string, connection_id?: number | null, deep = true) =>
    request<ReportFull>(`/reports/${rid}/generate`, {
      method: "POST",
      body: JSON.stringify({ prompt, connection_id, deep_analysis: deep }),
    }),
  reportAddBlock: (rid: number, kind: string, content: any) =>
    request<ReportFull>(`/reports/${rid}/blocks`, {
      method: "POST",
      body: JSON.stringify({ kind, content }),
    }),
  reportUpdateBlock: (rid: number, bid: number, content: any) =>
    request<ReportBlock>(`/reports/${rid}/blocks/${bid}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  reportDeleteBlock: (rid: number, bid: number) =>
    request<ReportFull>(`/reports/${rid}/blocks/${bid}`, { method: "DELETE" }),
  reportMoveBlock: (rid: number, bid: number, direction: "up" | "down") =>
    request<ReportFull>(`/reports/${rid}/blocks/${bid}/move`, {
      method: "POST",
      body: JSON.stringify({ direction }),
    }),
  reportAddAnswer: (rid: number, title: string, response: ChatResponse) =>
    request<ReportFull>(`/reports/${rid}/add-answer`, {
      method: "POST",
      body: JSON.stringify({ title, response }),
    }),
  reportExportUrl: (rid: number, format: "docx" | "pdf" | "md") =>
    `${API_BASE}/reports/${rid}/export?format=${format}`,

  // --- Conversations d'espace ---
  spaceConvList: (sid: number, archived = false) =>
    request<ConvSummary[]>(`/spaces/${sid}/conversations?archived=${archived}`),
  spaceConvGet: (sid: number, cid: number) =>
    request<ConvFull>(`/spaces/${sid}/conversations/${cid}`),
  spaceConvCreate: (sid: number, body: { title?: string; folder_id?: number | null }) =>
    request<ConvFull>(`/spaces/${sid}/conversations`, { method: "POST", body: JSON.stringify(body) }),
  spaceConvUpdate: (
    sid: number, cid: number,
    patch: { title?: string; folder_id?: number | null; archived?: boolean },
  ) =>
    request<ConvSummary>(`/spaces/${sid}/conversations/${cid}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  spaceConvDelete: (sid: number, cid: number) =>
    request<any>(`/spaces/${sid}/conversations/${cid}`, { method: "DELETE" }),
  spaceConvAddTurn: (sid: number, cid: number, connection_id: number, question: string, deep: boolean) =>
    request<{ turn: ConvTurn; conversation: ConvSummary }>(
      `/spaces/${sid}/conversations/${cid}/turns`,
      { method: "POST", body: JSON.stringify({ connection_id, question, deep_analysis: deep }) },
    ),
  spaceFolderList: (sid: number) =>
    request<ConvFolder[]>(`/spaces/${sid}/conversations/folders`),
  spaceFolderCreate: (sid: number, name: string) =>
    request<ConvFolder>(`/spaces/${sid}/conversations/folders`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  spaceFolderDelete: (sid: number, fid: number) =>
    request<any>(`/spaces/${sid}/conversations/folders/${fid}`, { method: "DELETE" }),
  mfaEnroll: () => request<{ secret: string; otpauth_uri: string }>("/auth/mfa/enroll", { method: "POST" }),
  mfaVerify: (code: string) =>
    request<void>("/auth/mfa/verify", { method: "POST", body: JSON.stringify({ code }) }),
  users: () => request<User[]>("/users"),
  createUser: (payload: any) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: any) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: "DELETE" }),
  userConnections: (id: number) => request<number[]>(`/users/${id}/connections`),
  grantConnection: (id: number, connection_id: number) =>
    request<void>(`/users/${id}/connections`, {
      method: "POST",
      body: JSON.stringify({ connection_id }),
    }),
  revokeConnection: (id: number, connection_id: number) =>
    request<void>(`/users/${id}/connections/${connection_id}`, { method: "DELETE" }),

  // --- Définitions métier (V0.4, portée tenant) ---
  definitions: () => request<BusinessDefinition[]>("/definitions"),
  createDefinition: (payload: any) =>
    request<BusinessDefinition>("/definitions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteDefinition: (defId: number) =>
    request<void>(`/definitions/${defId}`, { method: "DELETE" }),

  // --- Alertes (V0.4) ---
  alerts: (id: number) => request<Alert[]>(`/connections/${id}/alerts`),
  createAlert: (id: number, payload: any) =>
    request<Alert>(`/connections/${id}/alerts`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  checkAlert: (id: number, alertId: number) =>
    request<Alert>(`/connections/${id}/alerts/${alertId}/check`, { method: "POST" }),
  checkAllAlerts: (id: number) =>
    request<Alert[]>(`/connections/${id}/alerts/check-all`, { method: "POST" }),
  alertEvents: (id: number, alertId: number) =>
    request<AlertEvent[]>(`/connections/${id}/alerts/${alertId}/events`),
  deleteAlert: (id: number, alertId: number) =>
    request<void>(`/connections/${id}/alerts/${alertId}`, { method: "DELETE" }),

  // --- Préférences (V0.4, tenant) ---
  preferences: () => request<Preferences>("/settings/preferences"),
  updatePreferences: (payload: Partial<Preferences>) =>
    request<Preferences>("/settings/preferences", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
