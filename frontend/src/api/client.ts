const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8001/api/v1';
const TOKEN_KEY = 'aitesthub_token';

type ApiErrorOptions = {
  method: string;
  url: string;
  status?: number;
  statusText?: string;
  detail: string;
  hint?: string;
};

export class ApiClientError extends Error {
  method: string;
  url: string;
  status?: number;
  statusText?: string;
  detail: string;
  hint?: string;

  constructor(options: ApiErrorOptions) {
    super(formatApiError(options));
    this.name = 'ApiClientError';
    this.method = options.method;
    this.url = options.url;
    this.status = options.status;
    this.statusText = options.statusText;
    this.detail = options.detail;
    this.hint = options.hint;
  }
}

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
  const method = options.method ?? 'GET';
  const url = `${API_BASE}${path}`;
  const { headers: optionHeaders, ...fetchOptions } = options;
  let response: Response;

  try {
    response = await fetch(url, {
      ...fetchOptions,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(optionHeaders ?? {}),
      },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiClientError({
      method,
      url,
      detail: `浏览器没有收到后端响应：${detail}`,
      hint: '请检查后端服务是否启动、API 地址是否正确，以及浏览器控制台是否有 CORS 拦截信息。',
    });
  }

  if (!response.ok) {
    const responseText = await response.text();
    throw new ApiClientError({
      method,
      url,
      status: response.status,
      statusText: response.statusText,
      detail: formatResponseDetail(responseText),
    });
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function formatApiError(options: ApiErrorOptions) {
  const lines = [`请求失败：${options.method} ${options.url}`];
  if (options.status) {
    lines.push(`HTTP 状态：${options.status}${options.statusText ? ` ${options.statusText}` : ''}`);
  } else {
    lines.push('错误类型：网络连接失败或请求被浏览器拦截');
  }
  lines.push(`错误详情：${options.detail || '后端没有返回错误详情。'}`);
  if (options.hint) {
    lines.push(`排查建议：${options.hint}`);
  }
  return lines.join('\n');
}

function formatResponseDetail(responseText: string) {
  if (!responseText.trim()) {
    return '后端没有返回错误详情。';
  }

  try {
    const parsed = JSON.parse(responseText) as unknown;
    if (isRecord(parsed) && 'detail' in parsed) {
      return formatDetailValue(parsed.detail);
    }
    return JSON.stringify(parsed, null, 2);
  } catch {
    return responseText;
  }
}

function formatDetailValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(formatValidationItem).join('\n');
  }
  if (isRecord(value)) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function formatValidationItem(value: unknown): string {
  if (!isRecord(value)) {
    return String(value);
  }

  const location = Array.isArray(value.loc) ? value.loc.join('.') : '';
  const message = typeof value.msg === 'string' ? value.msg : JSON.stringify(value);
  return location ? `${location}: ${message}` : message;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function downloadFile(path: string): Promise<Blob> {
  const token = getToken();
  const url = `${API_BASE}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new ApiClientError({
      method: 'GET',
      url,
      detail: `浏览器没有收到后端响应：${detail}`,
      hint: '请检查后端服务是否启动、API 地址是否正确，以及浏览器控制台是否有 CORS 拦截信息。',
    });
  }

  if (!response.ok) {
    const responseText = await response.text();
    throw new ApiClientError({
      method: 'GET',
      url,
      status: response.status,
      statusText: response.statusText,
      detail: formatResponseDetail(responseText),
    });
  }
  return response.blob();
}

function buildUrl(path: string) {
  return `${API_BASE}${path}`;
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
  steps: Array<Record<string, unknown> & { order: number; action: string }>;
  expected_result: string;
  tags: string[];
  generated_by: string;
  review_comment?: string;
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
  ai_diagnosis?: {
    failure_type?: string;
    root_cause?: string;
    evidence?: string[];
    fix_suggestions?: string[];
    suggested_steps?: Array<Record<string, unknown> & { order?: number; action?: string }>;
    knowledge_type?: string;
    should_save_knowledge?: boolean;
    confidence?: number;
    diagnosed_by?: string;
  };
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
  generateCasesWithDoc: (payload: { project_id: number; title: string; content: string; file?: File }) => {
    const form = new FormData();
    form.append('project_id', String(payload.project_id));
    form.append('title', payload.title);
    form.append('content', payload.content);
    form.append('source_type', 'text');
    form.append('auto_save_requirement', 'true');
    if (payload.file) {
      form.append('file', payload.file);
    }
    return request<TestCase[]>('/requirements/generate-cases-with-doc', { method: 'POST', body: form });
  },
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
  diagnoseRunResult: (runId: number, resultId: number) =>
    request<RunResult>(`/runs/${runId}/results/${resultId}/diagnose`, { method: 'POST' }),
  saveDiagnosisKnowledge: (runId: number, resultId: number) =>
    request<Knowledge>(`/runs/${runId}/results/${resultId}/diagnosis-knowledge`, { method: 'POST' }),
  getRunArtifactUrl: (runId: number, artifactId: number) =>
    buildUrl(`/runs/${runId}/artifacts/${artifactId}/download`),
  downloadRunArtifact: (runId: number, artifactId: number) =>
    downloadFile(`/runs/${runId}/artifacts/${artifactId}/download`),
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
