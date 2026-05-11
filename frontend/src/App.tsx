import {
  CheckCircle2,
  Database,
  FileText,
  GitBranch,
  LayoutDashboard,
  Lock,
  LogOut,
  Pencil,
  Play,
  RefreshCcw,
  Save,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Trash2,
  UserPlus,
  XCircle,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  api,
  CiTrigger,
  clearToken,
  getToken,
  Knowledge,
  Project,
  ProjectEnvironment,
  setToken,
  TestCase,
  TestRun,
  User,
} from './api/client';

type ViewKey = 'overview' | 'requirements' | 'review' | 'runs' | 'knowledge' | 'environments';

const navItems: Array<{ key: ViewKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: 'overview', label: '总览', icon: LayoutDashboard },
  { key: 'requirements', label: '需求生成', icon: Sparkles },
  { key: 'review', label: '人工审核', icon: ShieldCheck },
  { key: 'runs', label: '测试执行', icon: Play },
  { key: 'knowledge', label: '知识库', icon: Database },
  { key: 'environments', label: '环境配置', icon: Server },
];

const statusLabel: Record<string, string> = {
  draft: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  queued: '排队中',
  running: '执行中',
  passed: '通过',
  failed: '失败',
  skipped: '跳过',
};

const emptyCase: Partial<TestCase> = {
  title: '',
  type: 'functional',
  priority: 'P2',
  preconditions: '',
  expected_result: '',
  tags: [],
  steps: [{ order: 1, action: '' }],
};

const usernamePattern = /^[A-Za-z0-9_]{4,32}$/;

export function App() {
  const [currentUser, setCurrentUser] = useState<User | undefined>();
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authUsername, setAuthUsername] = useState('admin_001');
  const [authDisplayName, setAuthDisplayName] = useState('平台管理员');
  const [authPassword, setAuthPassword] = useState('Admin12345');
  const [activeView, setActiveView] = useState<ViewKey>('overview');
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | undefined>();
  const [environments, setEnvironments] = useState<ProjectEnvironment[]>([]);
  const [cases, setCases] = useState<TestCase[]>([]);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [ciTriggers, setCiTriggers] = useState<CiTrigger[]>([]);
  const [selectedRun, setSelectedRun] = useState<TestRun | undefined>();
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [projectName, setProjectName] = useState('示例项目');
  const [requirement, setRequirement] = useState('用户可以登录系统，查看项目列表，提交测试任务，并查看测试报告。');
  const [environmentName, setEnvironmentName] = useState('本地环境');
  const [environmentUrl, setEnvironmentUrl] = useState('http://localhost:3000');
  const [knowledgeTitle, setKnowledgeTitle] = useState('登录模块测试经验');
  const [knowledgeContent, setKnowledgeContent] = useState('登录失败时需要覆盖空密码、错误密码、锁定账号和无权限账号。');
  const [knowledgeQuery, setKnowledgeQuery] = useState('登录');
  const [knowledgeImportType, setKnowledgeImportType] = useState('historical_defect');
  const [knowledgeImportSkill, setKnowledgeImportSkill] = useState('历史缺陷测试 skill');
  const [knowledgeImportScore, setKnowledgeImportScore] = useState(4);
  const [knowledgeImportFile, setKnowledgeImportFile] = useState<File | undefined>();
  const [editingCaseId, setEditingCaseId] = useState<number | undefined>();
  const [draftCase, setDraftCase] = useState<Partial<TestCase>>(emptyCase);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId],
  );

  const stats = useMemo(() => {
    const approved = cases.filter((item) => item.status === 'approved').length;
    const draft = cases.filter((item) => item.status === 'draft').length;
    const rejected = cases.filter((item) => item.status === 'rejected').length;
    const passedRuns = runs.filter((item) => item.status === 'passed').length;
    return { approved, draft, rejected, passedRuns };
  }, [cases, runs]);

  useEffect(() => {
    if (!getToken()) return;
    api.me()
      .then((user) => {
        setCurrentUser(user);
        return refresh();
      })
      .catch(() => {
        clearToken();
        setCurrentUser(undefined);
      });
  }, []);

  async function handleAuth() {
    const username = authUsername.trim();
    const displayName = authDisplayName.trim();
    if (!usernamePattern.test(username)) {
      setNotice('账号只能包含英文字母、数字、下划线，长度必须为 4-32 位。');
      return;
    }
    if (authPassword.length < 8 || authPassword.length > 64) {
      setNotice('密码长度必须为 8-64 位。');
      return;
    }
    if (/\s/.test(authPassword)) {
      setNotice('密码不能包含空格、换行或制表符。');
      return;
    }
    if (!/[A-Za-z]/.test(authPassword) || !/\d/.test(authPassword)) {
      setNotice('密码必须同时包含字母和数字。');
      return;
    }
    if (authMode === 'register' && (displayName.length < 2 || displayName.length > 30)) {
      setNotice('显示名称长度必须为 2-30 位。');
      return;
    }

    setLoading(true);
    try {
      const response =
        authMode === 'register'
          ? await api.register({ username, password: authPassword, display_name: displayName })
          : await api.login({ username, password: authPassword });
      setToken(response.access_token);
      setCurrentUser(response.user);
      setNotice(`${authMode === 'register' ? '注册' : '登录'}成功。`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '认证失败');
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearToken();
    setCurrentUser(undefined);
    setProjects([]);
    setCases([]);
    setRuns([]);
    setSelectedRun(undefined);
    setNotice('已退出登录。');
  }

  async function refresh(projectId: number | null | undefined = selectedProjectId) {
    const nextProjects = await api.listProjects();
    setProjects(nextProjects);
    const nextProjectId = projectId === null ? nextProjects[0]?.id : projectId ?? nextProjects[0]?.id;
    setSelectedProjectId(nextProjectId);
    if (nextProjectId) {
      const [nextCases, nextRuns, nextEnvironments, nextKnowledge, nextCiTriggers] = await Promise.all([
        api.listCases(nextProjectId),
        api.listRuns(nextProjectId),
        api.listEnvironments(nextProjectId),
        api.listKnowledge(nextProjectId),
        api.listCiTriggers(nextProjectId),
      ]);
      setCases(nextCases);
      setRuns(nextRuns);
      setEnvironments(nextEnvironments);
      setKnowledge(nextKnowledge);
      setCiTriggers(nextCiTriggers);
      if (selectedRun) {
        const updatedRun = nextRuns.find((item) => item.id === selectedRun.id);
        if (updatedRun) {
          setSelectedRun(await api.getRun(updatedRun.id));
        }
      }
    } else {
      setCases([]);
      setRuns([]);
      setEnvironments([]);
      setKnowledge([]);
      setCiTriggers([]);
      setSelectedRun(undefined);
    }
  }

  async function createProject() {
    setLoading(true);
    try {
      const project = await api.createProject({
        name: projectName,
        description: '用于验证 AITestHub 平台能力的项目。',
        default_branch: 'main',
      });
      setNotice(`已创建项目：${project.name}`);
      await refresh(project.id);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '创建项目失败');
    } finally {
      setLoading(false);
    }
  }

  async function deleteProject(project: Project) {
    if (currentUser?.role !== 'admin') {
      setNotice('当前账号没有项目删除权限。');
      return;
    }
    const confirmed = window.confirm(`确认删除项目“${project.name}”？该项目下的需求、用例、运行记录、环境和知识都会一并删除。`);
    if (!confirmed) return;
    setLoading(true);
    try {
      await api.deleteProject(project.id);
      setNotice(`已删除项目：${project.name}`);
      if (project.id === selectedProjectId) {
        setSelectedProjectId(undefined);
        setCases([]);
        setRuns([]);
        setEnvironments([]);
        setKnowledge([]);
        setCiTriggers([]);
        setSelectedRun(undefined);
      }
      await refresh(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除项目失败');
    } finally {
      setLoading(false);
    }
  }

  async function createEnvironment() {
    if (!selectedProjectId) return;
    await api.createEnvironment({
      project_id: selectedProjectId,
      name: environmentName,
      base_url: environmentUrl,
      variables: {},
      is_default: environments.length === 0,
    });
    setNotice('项目环境已保存。');
    await refresh(selectedProjectId);
  }

  async function generateCases() {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const generated = await api.generateCases({
        project_id: selectedProjectId,
        title: '页面输入需求',
        content: requirement,
      });
      setNotice(`Agent 已生成 ${generated.length} 条测试用例，等待人工审核。`);
      setActiveView('review');
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '生成用例失败');
    } finally {
      setLoading(false);
    }
  }

  function startEdit(testCase: TestCase) {
    setEditingCaseId(testCase.id);
    setDraftCase({
      ...testCase,
      steps: testCase.steps.map((step, index) => ({ order: index + 1, action: step.action })),
    });
  }

  async function saveCase() {
    if (!editingCaseId || !selectedProjectId) return;
    const steps = (draftCase.steps ?? []).filter((step) => step.action?.trim());
    await api.updateCase(editingCaseId, {
      title: draftCase.title,
      type: draftCase.type,
      priority: draftCase.priority,
      preconditions: draftCase.preconditions,
      expected_result: draftCase.expected_result,
      tags: draftCase.tags,
      steps,
    });
    setEditingCaseId(undefined);
    setNotice('测试用例已保存。');
    await refresh(selectedProjectId);
  }

  async function reviewCase(caseId: number, status: 'approved' | 'rejected') {
    if (!selectedProjectId) return;
    try {
      await api.reviewCase(caseId, status, status === 'approved' ? '人工审核通过' : '需要补充测试步骤或预期结果');
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '审核失败');
    }
  }

  async function runApprovedCases() {
    if (!selectedProjectId) return;
    const approvedIds = cases.filter((item) => item.status === 'approved').map((item) => item.id);
    setLoading(true);
    try {
      const run = await api.createRun({
        project_id: selectedProjectId,
        name: '人工触发回归测试',
        case_ids: approvedIds,
      });
      setNotice(`测试任务已提交，运行 ID：${run.id}`);
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '提交测试任务失败');
    } finally {
      setLoading(false);
    }
  }

  async function openRunDetail(runId: number) {
    const detail = await api.getRun(runId);
    setSelectedRun(detail);
  }

  async function createKnowledge() {
    if (!selectedProjectId) return;
    await api.createKnowledge({
      project_id: selectedProjectId,
      source_type: 'test_strategy',
      title: knowledgeTitle,
      content: knowledgeContent,
      status: 'active',
      skill_name: '人工录入测试经验',
      triggers: knowledgeTitle.split(/\s|,|，|、/).map((item) => item.trim()).filter(Boolean).slice(0, 8),
      quality_score: 3,
      metadata_: {},
    });
    setNotice('知识条目已保存。');
    await refresh(selectedProjectId);
  }

  async function searchKnowledge() {
    if (!selectedProjectId) return;
    const results = await api.searchKnowledge({ project_id: selectedProjectId, query: knowledgeQuery, limit: 8 });
    setKnowledge(results);
    setNotice(`找到 ${results.length} 条知识记录。`);
  }

  async function importKnowledgeFile() {
    if (!selectedProjectId || !knowledgeImportFile) {
      setNotice('请选择项目和要导入的文件。');
      return;
    }
    setLoading(true);
    try {
      const result = await api.importKnowledge({
        project_id: selectedProjectId,
        source_type: knowledgeImportType,
        skill_name: knowledgeImportSkill,
        quality_score: knowledgeImportScore,
        file: knowledgeImportFile,
      });
      setNotice(`已导入 ${result.imported} 条知识，跳过 ${result.skipped} 条。`);
      setKnowledgeImportFile(undefined);
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '导入知识失败');
    } finally {
      setLoading(false);
    }
  }

  if (!currentUser) {
    return (
      <AuthScreen
        mode={authMode}
        setMode={setAuthMode}
        username={authUsername}
        setUsername={setAuthUsername}
        displayName={authDisplayName}
        setDisplayName={setAuthDisplayName}
        password={authPassword}
        setPassword={setAuthPassword}
        submit={handleAuth}
        loading={loading}
        notice={notice}
      />
    );
  }
  const user = currentUser;

  function renderActiveView() {
    if (!selectedProjectId && activeView !== 'overview') {
      return <EmptyState title="请先创建或选择项目" description="平台的需求、用例、环境和报告都归属于具体项目。" />;
    }

    switch (activeView) {
      case 'overview':
        return <OverviewView stats={stats} cases={cases} runs={runs} environments={environments} knowledge={knowledge} ciTriggers={ciTriggers} />;
      case 'requirements':
        return (
          <RequirementsView
            requirement={requirement}
            setRequirement={setRequirement}
            generateCases={generateCases}
            loading={loading}
            selectedProject={selectedProject}
          />
        );
      case 'review':
        return (
          <ReviewView
            cases={cases}
            editingCaseId={editingCaseId}
            draftCase={draftCase}
            setDraftCase={setDraftCase}
            startEdit={startEdit}
            saveCase={saveCase}
            reviewCase={reviewCase}
            canReview={user.role === 'admin' || user.role === 'reviewer'}
          />
        );
      case 'runs':
        return (
          <RunsView
            runs={runs}
            ciTriggers={ciTriggers}
            selectedRun={selectedRun}
            runApprovedCases={runApprovedCases}
            openRunDetail={openRunDetail}
            loading={loading}
            selectedProjectId={selectedProjectId}
          />
        );
      case 'knowledge':
        return (
          <KnowledgeView
            knowledge={knowledge}
            knowledgeTitle={knowledgeTitle}
            knowledgeContent={knowledgeContent}
            knowledgeQuery={knowledgeQuery}
            setKnowledgeTitle={setKnowledgeTitle}
            setKnowledgeContent={setKnowledgeContent}
            setKnowledgeQuery={setKnowledgeQuery}
            createKnowledge={createKnowledge}
            searchKnowledge={searchKnowledge}
            importKnowledgeFile={importKnowledgeFile}
            importType={knowledgeImportType}
            setImportType={setKnowledgeImportType}
            importSkill={knowledgeImportSkill}
            setImportSkill={setKnowledgeImportSkill}
            importScore={knowledgeImportScore}
            setImportScore={setKnowledgeImportScore}
            importFile={knowledgeImportFile}
            setImportFile={setKnowledgeImportFile}
            loading={loading}
            selectedProjectId={selectedProjectId}
          />
        );
      case 'environments':
        return (
          <EnvironmentsView
            environments={environments}
            environmentName={environmentName}
            environmentUrl={environmentUrl}
            setEnvironmentName={setEnvironmentName}
            setEnvironmentUrl={setEnvironmentUrl}
            createEnvironment={createEnvironment}
            refresh={() => refresh(selectedProjectId)}
            selectedProjectId={selectedProjectId}
          />
        );
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-block">
          <div className="brand-mark">AI</div>
          <div>
            <p className="eyebrow">Agent + Human Review</p>
            <h1>AITestHub 自动化测试平台</h1>
          </div>
        </div>
        <div className="header-actions">
          <div className="user-chip">
            <strong>{user.display_name}</strong>
            <span>{user.role}</span>
          </div>
          <select value={selectedProjectId ?? ''} onChange={(event) => refresh(Number(event.target.value))}>
            <option value="">选择项目</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <button className="icon-button" onClick={() => refresh()} title="刷新数据">
            <RefreshCcw size={18} />
          </button>
          <button className="icon-button" onClick={logout} title="退出登录">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <nav className="top-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button key={item.key} className={activeView === item.key ? 'active' : ''} onClick={() => setActiveView(item.key)}>
              <Icon size={17} />
              {item.label}
            </button>
          );
        })}
      </nav>

      {notice && <div className="notice">{notice}</div>}

      <section className="project-strip">
        <div>
          <span>当前项目</span>
          <strong>{selectedProject?.name ?? '未选择'}</strong>
        </div>
        <div>
          <span>默认分支</span>
          <strong>{selectedProject?.default_branch ?? '-'}</strong>
        </div>
        <div>
          <span>已配置环境</span>
          <strong>{environments.length}</strong>
        </div>
      </section>

      <section className="content-shell">
        <aside className="project-dock">
          <PanelTitle icon={GitBranch} title="项目管理" />
          <div className="form-row">
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
            <button onClick={createProject} disabled={loading}>新建</button>
          </div>
          <div className="project-list">
            {projects.map((project) => (
              <button
                key={project.id}
                className={project.id === selectedProjectId ? 'project-item active' : 'project-item'}
                onClick={() => refresh(project.id)}
              >
                <span>
                  <strong>{project.name}</strong>
                  <small>{project.default_branch}</small>
                </span>
                {user.role === 'admin' && (
                  <span
                    className="project-delete"
                    role="button"
                    title="删除项目"
                    onClick={(event) => {
                      event.stopPropagation();
                      deleteProject(project);
                    }}
                  >
                    <Trash2 size={14} />
                  </span>
                )}
              </button>
            ))}
          </div>
        </aside>

        <section className="view-panel">{renderActiveView()}</section>
      </section>
    </main>
  );
}

function AuthScreen({
  mode,
  setMode,
  username,
  setUsername,
  displayName,
  setDisplayName,
  password,
  setPassword,
  submit,
  loading,
  notice,
}: {
  mode: 'login' | 'register';
  setMode: (mode: 'login' | 'register') => void;
  username: string;
  setUsername: (value: string) => void;
  displayName: string;
  setDisplayName: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  submit: () => void;
  loading: boolean;
  notice: string;
}) {
  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-block">
          <div className="brand-mark">AI</div>
          <div>
            <p className="eyebrow">AITestHub</p>
            <h1>{mode === 'login' ? '登录测试平台' : '注册平台账号'}</h1>
          </div>
        </div>
        <div className="auth-tabs">
          <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>
            <Lock size={16} />
            登录
          </button>
          <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>
            <UserPlus size={16} />
            注册
          </button>
        </div>
        {notice && <div className="notice">{notice}</div>}
        <label>
          账号
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        {mode === 'register' && (
          <label>
            显示名称
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
        )}
        <label>
          密码
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <p className="hint">账号只允许英文字母、数字、下划线，长度 4-32 位。密码长度 8-64 位，必须包含字母和数字。</p>
        <button className="wide-button" onClick={submit} disabled={loading}>
          {mode === 'login' ? '登录' : '注册并登录'}
        </button>
      </section>
    </main>
  );
}

function PanelTitle({ icon: Icon, title }: { icon: typeof GitBranch; title: string }) {
  return (
    <div className="panel-title">
      <Icon size={18} />
      <span>{title}</span>
    </div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}

function OverviewView({
  stats,
  cases,
  runs,
  environments,
  knowledge,
  ciTriggers,
}: {
  stats: { approved: number; draft: number; rejected: number; passedRuns: number };
  cases: TestCase[];
  runs: TestRun[];
  environments: ProjectEnvironment[];
  knowledge: Knowledge[];
  ciTriggers: CiTrigger[];
}) {
  return (
    <div className="view-stack">
      <div className="metric-grid">
        <Metric label="待审核用例" value={stats.draft} />
        <Metric label="已通过用例" value={stats.approved} />
        <Metric label="CI 触发记录" value={ciTriggers.length} />
        <Metric label="通过的运行" value={stats.passedRuns} />
      </div>
      <div className="two-column">
        <section className="panel">
          <PanelTitle icon={ShieldCheck} title="最近测试用例" />
          <CompactList items={cases.slice(0, 6).map((item) => `${item.priority} · ${item.title}`)} />
        </section>
        <section className="panel">
          <PanelTitle icon={Play} title="最近测试运行" />
          <CompactList items={runs.slice(0, 6).map((item) => `${statusLabel[item.status] ?? item.status} · ${item.name}`)} />
        </section>
      </div>
      <div className="two-column">
        <section className="panel">
          <PanelTitle icon={Server} title="测试环境" />
          <CompactList items={environments.slice(0, 6).map((item) => `${item.name} · ${item.base_url}`)} />
        </section>
        <section className="panel">
          <PanelTitle icon={Database} title="知识条目" />
          <CompactList items={knowledge.slice(0, 6).map((item) => item.title)} />
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <section className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </section>
  );
}

function CompactList({ items }: { items: string[] }) {
  if (!items.length) return <EmptyState title="暂无数据" description="完成相关操作后会在这里显示。" />;
  return (
    <div className="compact-list">
      {items.map((item) => (
        <div key={item}>{item}</div>
      ))}
    </div>
  );
}

function RequirementsView(props: {
  requirement: string;
  setRequirement: (value: string) => void;
  generateCases: () => void;
  loading: boolean;
  selectedProject?: Project;
}) {
  return (
    <section className="panel hero-panel">
      <PanelTitle icon={FileText} title="需求输入与用例生成" />
      <textarea value={props.requirement} onChange={(event) => props.setRequirement(event.target.value)} />
      <div className="actions">
        <span>{props.selectedProject ? `当前项目：${props.selectedProject.name}` : '请先创建项目'}</span>
        <button onClick={props.generateCases} disabled={!props.selectedProject || props.loading}>
          <Sparkles size={16} />
          生成测试用例
        </button>
      </div>
    </section>
  );
}

function ReviewView({
  cases,
  editingCaseId,
  draftCase,
  setDraftCase,
  startEdit,
  saveCase,
  reviewCase,
  canReview,
}: {
  cases: TestCase[];
  editingCaseId?: number;
  draftCase: Partial<TestCase>;
  setDraftCase: (value: Partial<TestCase>) => void;
  startEdit: (testCase: TestCase) => void;
  saveCase: () => void;
  reviewCase: (caseId: number, status: 'approved' | 'rejected') => void;
  canReview: boolean;
}) {
  return (
    <section className="panel">
      <PanelTitle icon={ShieldCheck} title="人工审核与用例编辑" />
      {!canReview && <div className="notice">当前账号可以编辑用例，但没有通过/驳回权限。</div>}
      <div className="case-list">
        {cases.map((testCase) => (
          <article className="case-item" key={testCase.id}>
            {editingCaseId === testCase.id ? (
              <div className="edit-form">
                <input value={draftCase.title ?? ''} onChange={(event) => setDraftCase({ ...draftCase, title: event.target.value })} />
                <div className="triple-row">
                  <input value={draftCase.type ?? ''} onChange={(event) => setDraftCase({ ...draftCase, type: event.target.value })} />
                  <input value={draftCase.priority ?? ''} onChange={(event) => setDraftCase({ ...draftCase, priority: event.target.value })} />
                  <input
                    value={(draftCase.tags ?? []).join(',')}
                    onChange={(event) => setDraftCase({ ...draftCase, tags: event.target.value.split(',').map((tag) => tag.trim()).filter(Boolean) })}
                  />
                </div>
                <textarea value={draftCase.preconditions ?? ''} onChange={(event) => setDraftCase({ ...draftCase, preconditions: event.target.value })} />
                <textarea
                  value={(draftCase.steps ?? []).map((step) => step.action).join('\n')}
                  onChange={(event) =>
                    setDraftCase({
                      ...draftCase,
                      steps: event.target.value.split('\n').map((action, index) => ({ order: index + 1, action })),
                    })
                  }
                />
                <textarea value={draftCase.expected_result ?? ''} onChange={(event) => setDraftCase({ ...draftCase, expected_result: event.target.value })} />
                <button className="ghost primary" onClick={saveCase}>
                  <Save size={15} />
                  保存
                </button>
              </div>
            ) : (
              <>
                <header>
                  <div>
                    <strong>{testCase.title}</strong>
                    <p>{testCase.expected_result}</p>
                  </div>
                  <span className={`badge ${testCase.status}`}>{statusLabel[testCase.status] ?? testCase.status}</span>
                </header>
                <ol>
                  {testCase.steps.map((step) => (
                    <li key={`${testCase.id}-${step.order}`}>{step.action}</li>
                  ))}
                </ol>
                {testCase.ai_review && Object.keys(testCase.ai_review).length > 0 && (
                  <AiReviewBox review={testCase.ai_review} />
                )}
                <footer>
                  <span>{testCase.priority} · {testCase.type} · {testCase.generated_by}</span>
                  <div>
                    <button className="ghost" onClick={() => startEdit(testCase)}>
                      <Pencil size={15} />
                      编辑
                    </button>
                    <button className="ghost" onClick={() => reviewCase(testCase.id, 'rejected')} disabled={!canReview}>
                      <XCircle size={15} />
                      驳回
                    </button>
                    <button className="ghost primary" onClick={() => reviewCase(testCase.id, 'approved')} disabled={!canReview}>
                      <CheckCircle2 size={15} />
                      通过
                    </button>
                  </div>
                </footer>
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function AiReviewBox({ review }: { review: NonNullable<TestCase['ai_review']> }) {
  const riskText: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' };
  const issues = [
    ...(review.missing ?? []).map((item) => `遗漏：${item}`),
    ...(review.contradictions ?? []).map((item) => `矛盾：${item}`),
    ...(review.out_of_scope ?? []).map((item) => `越界：${item}`),
    ...(review.duplicates ?? []).map((item) => `重复：${item}`),
    ...(review.suggestions ?? []).map((item) => `建议：${item}`),
  ];
  return (
    <div className="ai-review-box">
      <div>
        <strong>AI 自评审</strong>
        <span>{riskText[review.risk_level ?? ''] ?? '待人工确认'} · {review.score ?? 0} 分 · {review.reviewed_by ?? 'reviewer'}</span>
      </div>
      {issues.length > 0 && (
        <ul>
          {issues.slice(0, 6).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RunsView({
  runs,
  ciTriggers,
  selectedRun,
  runApprovedCases,
  openRunDetail,
  loading,
  selectedProjectId,
}: {
  runs: TestRun[];
  ciTriggers: CiTrigger[];
  selectedRun?: TestRun;
  runApprovedCases: () => void;
  openRunDetail: (runId: number) => void;
  loading: boolean;
  selectedProjectId?: number;
}) {
  return (
    <div className="two-column">
      <section className="panel">
        <PanelTitle icon={Play} title="测试执行" />
        <button className="run-button" onClick={runApprovedCases} disabled={!selectedProjectId || loading}>
          <Play size={17} />
          执行已通过用例
        </button>
        <div className="run-list">
          {runs.map((run) => (
            <article className="run-item" key={run.id}>
              <div>
                <strong>{run.name}</strong>
                <span className={`badge ${run.status}`}>{statusLabel[run.status] ?? run.status}</span>
              </div>
              <p>
                总数 {run.summary?.total ?? 0}，通过 {run.summary?.passed ?? 0}，失败 {run.summary?.failed ?? 0}
              </p>
              <button className="ghost primary" onClick={() => openRunDetail(run.id)}>查看详情</button>
            </article>
          ))}
        </div>
        <PanelTitle icon={GitBranch} title="CI 触发记录" />
        <div className="mini-list">
          {ciTriggers.map((trigger) => (
            <div className="knowledge-item" key={trigger.id}>
              <strong>{trigger.provider} · Run #{trigger.run_id}</strong>
              <p>分支：{trigger.branch ?? '-'} · 提交：{trigger.commit_sha ?? '-'}</p>
              <p>变更文件：{trigger.changed_files.length}</p>
            </div>
          ))}
        </div>
      </section>
      <section className="panel report-detail">
        <PanelTitle icon={FileText} title="测试报告详情" />
        {!selectedRun ? (
          <EmptyState title="请选择一次测试运行" description="点击左侧运行记录的“查看详情”查看报告、结果和 CI 信息。" />
        ) : (
          <>
            <div className="detail-grid">
              <Detail label="运行 ID" value={`#${selectedRun.id}`} />
              <Detail label="状态" value={statusLabel[selectedRun.status] ?? selectedRun.status} />
              <Detail label="触发方式" value={selectedRun.trigger_type} />
              <Detail label="分支" value={selectedRun.branch ?? '-'} />
              <Detail label="提交" value={selectedRun.commit_sha ?? '-'} />
            </div>
            {selectedRun.report && <pre>{selectedRun.report}</pre>}
            <PanelTitle icon={ShieldCheck} title="用例结果" />
            <div className="mini-list">
              {(selectedRun.results ?? []).map((result) => (
                <div className="knowledge-item" key={result.id}>
                  <strong>Case #{result.case_id ?? '-'} · {statusLabel[result.status] ?? result.status}</strong>
                  <p>{result.message}</p>
                  {result.logs && <pre>{result.logs}</pre>}
                </div>
              ))}
            </div>
            {selectedRun.ci_trigger && (
              <>
                <PanelTitle icon={GitBranch} title="CI 触发详情" />
                <div className="detail-grid">
                  <Detail label="来源" value={selectedRun.ci_trigger.provider} />
                  <Detail label="分支" value={selectedRun.ci_trigger.branch ?? '-'} />
                  <Detail label="提交" value={selectedRun.ci_trigger.commit_sha ?? '-'} />
                  <Detail label="文件数" value={String(selectedRun.ci_trigger.changed_files.length)} />
                </div>
                <pre>{JSON.stringify(selectedRun.ci_trigger.payload, null, 2)}</pre>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function KnowledgeView(props: {
  knowledge: Knowledge[];
  knowledgeTitle: string;
  knowledgeContent: string;
  knowledgeQuery: string;
  setKnowledgeTitle: (value: string) => void;
  setKnowledgeContent: (value: string) => void;
  setKnowledgeQuery: (value: string) => void;
  createKnowledge: () => void;
  searchKnowledge: () => void;
  importKnowledgeFile: () => void;
  importType: string;
  setImportType: (value: string) => void;
  importSkill: string;
  setImportSkill: (value: string) => void;
  importScore: number;
  setImportScore: (value: number) => void;
  importFile?: File;
  setImportFile: (value?: File) => void;
  loading: boolean;
  selectedProjectId?: number;
}) {
  return (
    <section className="panel knowledge-panel">
      <PanelTitle icon={Database} title="测试知识库" />
      <div className="two-column compact-form">
        <div>
          <div className="import-box">
            <strong>批量导入</strong>
            <select value={props.importType} onChange={(event) => props.setImportType(event.target.value)}>
              <option value="requirement">需求文档</option>
              <option value="historical_defect">历史缺陷</option>
              <option value="business_rule">业务规则</option>
              <option value="test_strategy">测试策略</option>
            </select>
            <input value={props.importSkill} onChange={(event) => props.setImportSkill(event.target.value)} />
            <input
              type="number"
              min={1}
              max={5}
              value={props.importScore}
              onChange={(event) => props.setImportScore(Number(event.target.value))}
            />
            <input
              type="file"
              accept=".txt,.md,.csv,.json,text/plain,text/markdown,application/json,text/csv"
              onChange={(event) => props.setImportFile(event.target.files?.[0])}
            />
            <button className="wide-button" onClick={props.importKnowledgeFile} disabled={!props.selectedProjectId || !props.importFile || props.loading}>
              导入文件
            </button>
            {props.importFile && <p>已选择：{props.importFile.name}</p>}
          </div>
          <input value={props.knowledgeTitle} onChange={(event) => props.setKnowledgeTitle(event.target.value)} />
          <textarea value={props.knowledgeContent} onChange={(event) => props.setKnowledgeContent(event.target.value)} />
          <button className="wide-button" onClick={props.createKnowledge} disabled={!props.selectedProjectId}>保存知识</button>
        </div>
        <div>
          <div className="search-row">
            <input value={props.knowledgeQuery} onChange={(event) => props.setKnowledgeQuery(event.target.value)} />
            <button onClick={props.searchKnowledge} disabled={!props.selectedProjectId}>
              <Search size={16} />
            </button>
          </div>
          <div className="mini-list">
            {props.knowledge.map((item) => (
              <div className="knowledge-item" key={item.id}>
                <strong>{item.title}</strong>
                <div className="knowledge-meta">
                  <span>{item.source_type}</span>
                  <span>{item.status}</span>
                  <span>{item.skill_name ?? '通用 skill'}</span>
                  <span>质量分 {item.quality_score}</span>
                </div>
                <p>{item.content}</p>
                {item.triggers?.length > 0 && <p>触发词：{item.triggers.join('、')}</p>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function EnvironmentsView(props: {
  environments: ProjectEnvironment[];
  environmentName: string;
  environmentUrl: string;
  setEnvironmentName: (value: string) => void;
  setEnvironmentUrl: (value: string) => void;
  createEnvironment: () => void;
  refresh: () => void;
  selectedProjectId?: number;
}) {
  return (
    <section className="panel">
      <PanelTitle icon={Server} title="项目环境配置" />
      <div className="environment-grid">
        <div className="environment-form">
          <input value={props.environmentName} onChange={(event) => props.setEnvironmentName(event.target.value)} />
          <input value={props.environmentUrl} onChange={(event) => props.setEnvironmentUrl(event.target.value)} />
          <button className="wide-button" onClick={props.createEnvironment} disabled={!props.selectedProjectId}>保存环境</button>
        </div>
        <div className="mini-list">
          {props.environments.map((environment) => (
            <div className="mini-item" key={environment.id}>
              <div>
                <strong>{environment.name}</strong>
                <span>{environment.base_url}</span>
              </div>
              <button title="删除环境" onClick={() => api.deleteEnvironment(environment.id).then(props.refresh)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
