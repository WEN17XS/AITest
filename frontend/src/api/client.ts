const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001/api/v1';
const TOKEN_KEY = 'aitesthub_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type User = {
  id: number;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: User;
};

export type Project = {
  id: number;
  name: string;
  description?: string;
  repo_url?: string;
  default_branch: string;
};

export type ProjectEnvironment = {
  id: number;
  project_id: number;
  name: string;
  base_url: string;
  variables: Record<string, unknown>;
  is_default: boolean;
};

export type TestCase = {
  id: number;
  project_id: number;
  title: string;
  type: string;
  priority: string;
  status: string;
  preconditions?: string;
  steps: Array<{ order: number; action: string }>;
  expected_result: string;
  tags: string[];
  generated_by: string;
  ai_review?: {
    risk_level?: string;
    score?: number;
    missing?: string[];
    contradictions?: string[];
    out_of_scope?: string[];
    duplicates?: string[];
    suggestions?: string[];
    verdict?: string;
    reviewed_by?: string;
  };
};

export type RunResult = {
  id: number;
  case_id?: number;
  status: string;
  duration_ms: number;
  message?: string;
  logs?: string;
  artifacts: string[];
};

export type CiTrigger = {
  id: number;
  run_id: number;
  project_id: number;
  provider: string;
  branch?: string;
  commit_sha?: string;
  changed_files: string[];
  payload: Record<string, unknown>;
  status: string;
  created_at: string;
};

export type RunArtifact = {
  id: number;
  run_id: number;
  result_id?: number;
  artifact_type: string;
  name: string;
  path: string;
  content_type?: string;
  size_bytes: number;
  metadata_: Record<string, unknown>;
  created_at: string;
};

export type TestRun = {
  id: number;
  project_id: number;
  environment_id?: number;
  name: string;
  trigger_type: string;
  executor_type: string;
  executor_config: Record<string, unknown>;
  status: string;
  branch?: string;
  commit_sha?: string;
  changed_files: string[];
  summary: Record<string, number>;
  report?: string;
  error_message?: string;
  results?: RunResult[];
  artifacts?: RunArtifact[];
  ci_trigger?: CiTrigger;
};

export type Knowledge = {
  id: number;
  project_id: number;
  source_type: string;
  source_id?: string;
  title: string;
  content: string;
  status: string;
  skill_name?: string;
  triggers: string[];
  quality_score: number;
  metadata_: Record<string, unknown>;
};

export type KnowledgeImportResult = {
  imported: number;
  skipped: number;
  items: Knowledge[];
};

export const api = {
  register: (payload: { username: string; password: string; display_name: string }) =>
    request<AuthResponse>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: (payload: { username: string; password: string }) =>
    request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  me: () => request<User>('/auth/me'),

  listProjects: () => request<Project[]>('/projects'),
  createProject: (payload: Partial<Project>) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  deleteProject: (projectId: number) =>
    request<{ status: string }>(`/projects/${projectId}`, { method: 'DELETE' }),

  listEnvironments: (projectId: number) => request<ProjectEnvironment[]>(`/environments?project_id=${projectId}`),
  createEnvironment: (payload: Omit<ProjectEnvironment, 'id'>) =>
    request<ProjectEnvironment>('/environments', { method: 'POST', body: JSON.stringify(payload) }),
  deleteEnvironment: (environmentId: number) =>
    request<{ status: string }>(`/environments/${environmentId}`, { method: 'DELETE' }),

  generateCases: (payload: { project_id: number; title: string; content: string }) =>
    request<TestCase[]>('/requirements/generate-cases', { method: 'POST', body: JSON.stringify(payload) }),
  listCases: (projectId?: number) =>
    request<TestCase[]>(`/test-cases${projectId ? `?project_id=${projectId}` : ''}`),
  updateCase: (caseId: number, payload: Partial<TestCase>) =>
    request<TestCase>(`/test-cases/${caseId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  reviewCase: (caseId: number, status: string, review_comment?: string) =>
    request<TestCase>(`/test-cases/${caseId}/review`, {
      method: 'PATCH',
      body: JSON.stringify({ status, review_comment }),
    }),

  createRun: (payload: {
    project_id: number;
    environment_id?: number;
    name: string;
    case_ids?: number[];
    executor_type?: string;
    executor_config?: Record<string, unknown>;
  }) =>
    request<TestRun>('/runs', { method: 'POST', body: JSON.stringify(payload) }),
  listRuns: (projectId?: number) => request<TestRun[]>(`/runs${projectId ? `?project_id=${projectId}` : ''}`),
  getRun: (runId: number) => request<TestRun>(`/runs/${runId}`),
  listCiTriggers: (projectId?: number) => request<CiTrigger[]>(`/ci/triggers${projectId ? `?project_id=${projectId}` : ''}`),

  listKnowledge: (projectId: number) => request<Knowledge[]>(`/knowledge?project_id=${projectId}`),
  createKnowledge: (payload: Omit<Knowledge, 'id' | 'status' | 'triggers' | 'quality_score'> & Partial<Pick<Knowledge, 'status' | 'triggers' | 'quality_score'>>) =>
    request<Knowledge>('/knowledge', { method: 'POST', body: JSON.stringify(payload) }),
  importKnowledge: (payload: {
    project_id: number;
    source_type: string;
    status?: string;
    skill_name?: string;
    quality_score?: number;
    file: File;
  }) => {
    const form = new FormData();
    form.append('project_id', String(payload.project_id));
    form.append('source_type', payload.source_type);
    form.append('status', payload.status ?? 'active');
    form.append('skill_name', payload.skill_name ?? '');
    form.append('quality_score', String(payload.quality_score ?? 3));
    form.append('file', payload.file);
    return request<KnowledgeImportResult>('/knowledge/import', { method: 'POST', body: form });
  },
  searchKnowledge: (payload: { project_id: number; query: string; limit?: number }) =>
    request<Knowledge[]>('/knowledge/search', { method: 'POST', body: JSON.stringify(payload) }),
};
