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
  RunArtifact,
  RunResult,
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
  type: 'web_ui',
  priority: 'P2',
  preconditions: '',
  expected_result: '',
  tags: [],
  steps: [{ order: 1, action: '' }],
};

const usernamePattern = /^[A-Za-z0-9_]{4,32}$/;
type ReviewStatusFilter = 'draft' | 'approved' | 'rejected' | 'all';
type CaseTypeFilter = 'all' | 'web_ui' | 'api' | 'pytest' | 'command' | 'integration' | 'functional' | 'regression' | 'security' | 'manual';
type ExecutorType = 'mock' | 'playwright' | 'api' | 'pytest' | 'command';

export function App() {
  const [currentUser, setCurrentUser] = useState<User | undefined>();
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authUsername, setAuthUsername] = useState('admin');
  const [authDisplayName, setAuthDisplayName] = useState('平台管理员');
  const [authPassword, setAuthPassword] = useState('');
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
  const [requirementDocFile, setRequirementDocFile] = useState<File | undefined>();
  const [environmentName, setEnvironmentName] = useState('本地环境');
  const [environmentUrl, setEnvironmentUrl] = useState('http://localhost:3000');
  const [environmentVariables, setEnvironmentVariables] = useState('{}');
  const [knowledgeTitle, setKnowledgeTitle] = useState('登录模块测试经验');
  const [knowledgeContent, setKnowledgeContent] = useState('登录失败时需要覆盖空密码、错误密码、锁定账号和无权限账号。');
  const [knowledgeQuery, setKnowledgeQuery] = useState('登录');
  const [knowledgeImportType, setKnowledgeImportType] = useState('historical_defect');
  const [knowledgeImportSkill, setKnowledgeImportSkill] = useState('历史缺陷测试 skill');
  const [knowledgeImportScore, setKnowledgeImportScore] = useState(4);
  const [knowledgeImportFile, setKnowledgeImportFile] = useState<File | undefined>();
  const [editingCaseId, setEditingCaseId] = useState<number | undefined>();
  const [draftCase, setDraftCase] = useState<Partial<TestCase>>(emptyCase);
  const [reviewStatusFilter, setReviewStatusFilter] = useState<ReviewStatusFilter>('draft');
  const [reviewTypeFilter, setReviewTypeFilter] = useState<CaseTypeFilter>('all');
  const [runExecutorType, setRunExecutorType] = useState<ExecutorType>('mock');
  const [runEnvironmentId, setRunEnvironmentId] = useState<number | undefined>();
  const [runHeadless, setRunHeadless] = useState(true);
  const [runTimeoutMs, setRunTimeoutMs] = useState(30000);
  const [selectedRunCaseIds, setSelectedRunCaseIds] = useState<number[]>([]);
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

  async function refreshWithNotice(projectId: number | null | undefined = selectedProjectId) {
    setLoading(true);
    try {
      await refresh(projectId);
      setNotice('数据已刷新。');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '刷新数据失败');
    } finally {
      setLoading(false);
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
    setLoading(true);
    try {
      let variables: Record<string, unknown> = {};
      try {
        variables = environmentVariables.trim() ? JSON.parse(environmentVariables) : {};
        if (!variables || Array.isArray(variables) || typeof variables !== 'object') {
          throw new Error('环境变量必须是 JSON 对象');
        }
      } catch (error) {
        setNotice(error instanceof Error ? `环境变量格式错误：${error.message}` : '环境变量格式错误');
        return;
      }
      await api.createEnvironment({
        project_id: selectedProjectId,
        name: environmentName,
        base_url: environmentUrl,
        variables,
        is_default: environments.length === 0,
      });
      setNotice('项目环境已保存。');
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '保存项目环境失败');
    } finally {
      setLoading(false);
    }
  }

  async function deleteEnvironment(environmentId: number) {
    setLoading(true);
    try {
      await api.deleteEnvironment(environmentId);
      setNotice('项目环境已删除。');
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除项目环境失败');
    } finally {
      setLoading(false);
    }
  }

  async function generateCases() {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const payload = {
        project_id: selectedProjectId,
        title: requirementDocFile ? `需求生成：${requirementDocFile.name}` : '页面输入需求',
        content: requirement,
      };
      const generated = requirementDocFile
        ? await api.generateCasesWithDoc({ ...payload, file: requirementDocFile })
        : await api.generateCases(payload);
      setNotice(`Agent 已生成 ${generated.length} 条测试用例，等待人工审核。`);
      setRequirementDocFile(undefined);
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
      steps: testCase.steps.map((step, index) => ({ ...step, order: step.order ?? index + 1 })),
    });
  }

  async function saveCase() {
    if (!editingCaseId || !selectedProjectId) return;
    setLoading(true);
    try {
      const steps = normalizeDraftSteps(draftCase.steps ?? []);
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
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '保存测试用例失败');
    } finally {
      setLoading(false);
    }
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
    const runnableCases = cases.filter((item) => isRunnableByExecutor(item, runExecutorType));
    const runnableIds = runnableCases.map((item) => item.id);
    const selectedIds = selectedRunCaseIds.filter((id) => runnableIds.includes(id));
    if (!runnableIds.length) {
      setNotice(`没有可由 ${executorLabel(runExecutorType)} 执行的已通过用例。`);
      return;
    }
    if (!selectedIds.length) {
      setNotice('请选择至少一条要执行的测试用例。');
      return;
    }
    setLoading(true);
    try {
      const run = await api.createRun({
        project_id: selectedProjectId,
        environment_id: runEnvironmentId,
        name: `人工触发 ${executorLabel(runExecutorType)} 测试`,
        case_ids: selectedIds,
        executor_type: runExecutorType,
        executor_config: executorConfig(runExecutorType, runHeadless, runTimeoutMs),
      });
      setNotice(`测试任务已提交，运行 ID：${run.id}`);
      await refresh(selectedProjectId);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '提交测试任务失败');
    } finally {
      setLoading(false);
    }
  }

  async function runSingleCase(testCase: TestCase) {
    if (!selectedProjectId) return;
    if (testCase.status !== 'approved') {
      setNotice('只有已通过的测试用例可以执行，请先完成人工审核。');
      return;
    }
    const executorType = defaultExecutorForCase(testCase);
    setLoading(true);
    try {
      const run = await api.createRun({
        project_id: selectedProjectId,
        environment_id: ['playwright', 'api', 'pytest', 'command'].includes(executorType) ? runEnvironmentId : undefined,
        name: `单条执行：${testCase.title}`,
        case_ids: [testCase.id],
        executor_type: executorType,
        executor_config: executorConfig(executorType, runHeadless, runTimeoutMs),
      });
      setActiveView('runs');
      setRunExecutorType(executorType);
      setSelectedRunCaseIds([testCase.id]);
      setNotice(`单条测试任务已提交，运行 ID：${run.id}`);
      await refresh(selectedProjectId);
      const detail = await api.getRun(run.id);
      setSelectedRun(detail);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '提交单条测试任务失败');
    } finally {
      setLoading(false);
    }
  }

  async function openRunDetail(runId: number) {
    try {
      const detail = await api.getRun(runId);
      setSelectedRun(detail);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '获取运行详情失败');
    }
  }

  async function openRunArtifact(artifact: RunArtifact) {
    try {
      const blob = await api.downloadRunArtifact(artifact.run_id, artifact.id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '打开运行附件失败');
    }
  }

  async function diagnoseRunResult(runId: number, resultId: number) {
    setLoading(true);
    try {
      await api.diagnoseRunResult(runId, resultId);
      const detail = await api.getRun(runId);
      setSelectedRun(detail);
      setNotice('失败归因已生成。');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '生成失败归因失败');
    } finally {
      setLoading(false);
    }
  }

  async function saveDiagnosisKnowledge(runId: number, resultId: number) {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const knowledgeItem = await api.saveDiagnosisKnowledge(runId, resultId);
      const detail = await api.getRun(runId);
      setSelectedRun(detail);
      setKnowledge(await api.listKnowledge(selectedProjectId));
      setNotice(`失败归因已沉淀到知识库：${knowledgeItem.title}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '沉淀失败归因知识失败');
    } finally {
      setLoading(false);
    }
  }

  async function applyDiagnosisSteps(runId: number, result: RunResult) {
    if (!selectedProjectId || !result.case_id) return;
    const suggestedSteps = result.ai_diagnosis?.suggested_steps ?? [];
    if (!suggestedSteps.length) {
      setNotice('当前归因没有可应用的修复步骤。');
      return;
    }
    const confirmed = window.confirm('确认将建议修复步骤应用到关联测试用例？用例会回到待审核状态。');
    if (!confirmed) return;

    setLoading(true);
    try {
      const steps = normalizeDraftSteps(suggestedSteps as TestCase['steps']);
      const updatedCase = await api.updateCase(result.case_id, {
        steps,
        status: 'draft',
        review_comment: `已从 Run #${runId} 的失败归因应用建议修复步骤，等待人工复核。`,
      });
      const detail = await api.getRun(runId);
      setSelectedRun(detail);
      await refresh(selectedProjectId);
      setActiveView('review');
      setEditingCaseId(result.case_id);
      setDraftCase({
        ...updatedCase,
        steps: updatedCase.steps.map((step, index) => ({ ...step, order: step.order ?? index + 1 })),
      });
      setNotice('建议修复步骤已应用到测试用例，请在人工审核页复核后再通过。');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '应用建议修复步骤失败');
    } finally {
      setLoading(false);
    }
  }

  async function createKnowledge() {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
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
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '保存知识条目失败');
    } finally {
      setLoading(false);
    }
  }

  async function searchKnowledge() {
    if (!selectedProjectId) return;
    setLoading(true);
    try {
      const results = await api.searchKnowledge({ project_id: selectedProjectId, query: knowledgeQuery, limit: 8 });
      setKnowledge(results);
      setNotice(`找到 ${results.length} 条知识记录。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '搜索知识库失败');
    } finally {
      setLoading(false);
    }
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
            docFile={requirementDocFile}
            setDocFile={setRequirementDocFile}
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
            runSingleCase={runSingleCase}
            canReview={user.role === 'admin' || user.role === 'reviewer'}
            statusFilter={reviewStatusFilter}
            setStatusFilter={setReviewStatusFilter}
            typeFilter={reviewTypeFilter}
            setTypeFilter={setReviewTypeFilter}
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
            openRunArtifact={openRunArtifact}
            diagnoseRunResult={diagnoseRunResult}
            saveDiagnosisKnowledge={saveDiagnosisKnowledge}
            applyDiagnosisSteps={applyDiagnosisSteps}
            loading={loading}
            selectedProjectId={selectedProjectId}
            cases={cases}
            environments={environments}
            executorType={runExecutorType}
            setExecutorType={(value) => {
              setRunExecutorType(value);
              setSelectedRunCaseIds([]);
            }}
            environmentId={runEnvironmentId}
            setEnvironmentId={setRunEnvironmentId}
            headless={runHeadless}
            setHeadless={setRunHeadless}
            timeoutMs={runTimeoutMs}
            setTimeoutMs={setRunTimeoutMs}
            selectedCaseIds={selectedRunCaseIds}
            setSelectedCaseIds={setSelectedRunCaseIds}
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
            environmentVariables={environmentVariables}
            setEnvironmentName={setEnvironmentName}
            setEnvironmentUrl={setEnvironmentUrl}
            setEnvironmentVariables={setEnvironmentVariables}
            createEnvironment={createEnvironment}
            deleteEnvironment={deleteEnvironment}
            refresh={() => refreshWithNotice(selectedProjectId)}
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
          <select value={selectedProjectId ?? ''} onChange={(event) => refreshWithNotice(Number(event.target.value))}>
            <option value="">选择项目</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <button className="icon-button" onClick={() => refreshWithNotice()} title="刷新数据">
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
                onClick={() => refreshWithNotice(project.id)}
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

function normalizeDraftSteps(steps: TestCase['steps']) {
  return steps
    .map((step, index) => ({ ...step, order: step.order ?? index + 1, action: String(step.action ?? '').trim() }))
    .filter((step) => step.action);
}

function formatStepsForEditor(steps: TestCase['steps']) {
  return JSON.stringify(steps.map((step, index) => ({ ...step, order: step.order ?? index + 1 })), null, 2);
}

function parseStepsFromEditor(value: string): TestCase['steps'] {
  const text = value.trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed.map((step, index) => ({
        ...(typeof step === 'object' && step !== null ? step : { action: String(step) }),
        order: Number(step?.order ?? index + 1),
        action: String(step?.action ?? '').trim(),
      }));
    }
  } catch {
    // 非 JSON 时按旧的逐行文本步骤处理。
  }
  return value.split('\n').map((action, index) => ({ order: index + 1, action }));
}

function executorLabel(executorType: ExecutorType) {
  return {
    mock: '模拟',
    playwright: 'Playwright',
    api: 'API',
    pytest: 'pytest',
    command: '命令',
  }[executorType];
}

function isRunnableByExecutor(testCase: TestCase, executorType: ExecutorType) {
  if (testCase.status !== 'approved') return false;
  if (executorType === 'playwright') return testCase.type === 'web_ui';
  if (executorType === 'api') return testCase.type === 'api';
  if (executorType === 'pytest') return ['pytest', 'integration', 'regression'].includes(testCase.type);
  if (executorType === 'command') return ['command', 'integration', 'regression'].includes(testCase.type);
  return true;
}

function defaultExecutorForCase(testCase: TestCase): ExecutorType {
  if (testCase.type === 'web_ui') return 'playwright';
  if (testCase.type === 'api') return 'api';
  if (testCase.type === 'pytest') return 'pytest';
  if (testCase.type === 'command') return 'command';
  return 'mock';
}

function executorConfig(executorType: ExecutorType, headless: boolean, timeoutMs: number) {
  if (executorType === 'playwright') {
    return { browser: 'chromium', headless, timeout_ms: timeoutMs, screenshot_on_failure: true };
  }
  if (executorType === 'api') {
    return { timeout_ms: timeoutMs, follow_redirects: true };
  }
  if (executorType === 'pytest' || executorType === 'command') {
    return { timeout_seconds: Math.max(1, Math.ceil(timeoutMs / 1000)) };
  }
  return {};
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
  docFile?: File;
  setDocFile: (value?: File) => void;
  generateCases: () => void;
  loading: boolean;
  selectedProject?: Project;
}) {
  return (
    <section className="panel hero-panel">
      <PanelTitle icon={FileText} title="需求输入与用例生成" />
      <textarea value={props.requirement} onChange={(event) => props.setRequirement(event.target.value)} />
      <div className="import-box requirement-doc-box">
        <strong>接口文档</strong>
        <input
          type="file"
          accept=".txt,.md,.csv,.json,.pdf"
          onChange={(event) => props.setDocFile(event.target.files?.[0])}
        />
        <p>{props.docFile ? `已选择：${props.docFile.name}` : '可直接上传接口文档，生成时会作为本次上下文解析，不需要先导入知识库。'}</p>
        {props.docFile && (
          <button type="button" className="ghost-button" onClick={() => props.setDocFile(undefined)}>
            清除文档
          </button>
        )}
      </div>
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
  runSingleCase,
  canReview,
  statusFilter,
  setStatusFilter,
  typeFilter,
  setTypeFilter,
}: {
  cases: TestCase[];
  editingCaseId?: number;
  draftCase: Partial<TestCase>;
  setDraftCase: (value: Partial<TestCase>) => void;
  startEdit: (testCase: TestCase) => void;
  saveCase: () => void;
  reviewCase: (caseId: number, status: 'approved' | 'rejected') => void;
  runSingleCase: (testCase: TestCase) => void;
  canReview: boolean;
  statusFilter: ReviewStatusFilter;
  setStatusFilter: (value: ReviewStatusFilter) => void;
  typeFilter: CaseTypeFilter;
  setTypeFilter: (value: CaseTypeFilter) => void;
}) {
  const filteredCases = cases.filter((testCase) => {
    const matchesStatus = statusFilter === 'all' || testCase.status === statusFilter;
    const matchesType = typeFilter === 'all' || testCase.type === typeFilter;
    return matchesStatus && matchesType;
  });
  const statusCounts = {
    draft: cases.filter((item) => item.status === 'draft').length,
    approved: cases.filter((item) => item.status === 'approved').length,
    rejected: cases.filter((item) => item.status === 'rejected').length,
  };

  return (
    <section className="panel">
      <PanelTitle icon={ShieldCheck} title="人工审核与用例编辑" />
      {!canReview && <div className="notice">当前账号可以编辑用例，但没有通过/驳回权限。</div>}
      <div className="review-toolbar">
        <div className="review-tabs">
          <button className={statusFilter === 'draft' ? 'active' : ''} onClick={() => setStatusFilter('draft')}>
            待审核 <span>{statusCounts.draft}</span>
          </button>
          <button className={statusFilter === 'approved' ? 'active' : ''} onClick={() => setStatusFilter('approved')}>
            已通过 <span>{statusCounts.approved}</span>
          </button>
          <button className={statusFilter === 'rejected' ? 'active' : ''} onClick={() => setStatusFilter('rejected')}>
            已驳回 <span>{statusCounts.rejected}</span>
          </button>
          <button className={statusFilter === 'all' ? 'active' : ''} onClick={() => setStatusFilter('all')}>
            全部 <span>{cases.length}</span>
          </button>
        </div>
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value as CaseTypeFilter)}>
          <option value="all">全部类型</option>
          <option value="web_ui">UI 自动化</option>
          <option value="api">接口/API</option>
          <option value="pytest">pytest</option>
          <option value="command">命令</option>
          <option value="integration">集成</option>
          <option value="functional">功能</option>
          <option value="regression">回归</option>
          <option value="security">安全</option>
          <option value="manual">人工</option>
        </select>
      </div>
      <div className="review-summary">
        <span>当前列表</span>
        <strong>{filteredCases.length}</strong>
      </div>
      <div className="case-list">
        {filteredCases.length === 0 && <EmptyState title="没有匹配的测试用例" description="切换审核状态或类型筛选后再查看。" />}
        {filteredCases.map((testCase) => (
          <article className="case-item" key={testCase.id}>
            {editingCaseId === testCase.id ? (
              <div className="edit-form">
                <input value={draftCase.title ?? ''} onChange={(event) => setDraftCase({ ...draftCase, title: event.target.value })} />
                <div className="triple-row">
                  <select value={draftCase.type ?? 'web_ui'} onChange={(event) => setDraftCase({ ...draftCase, type: event.target.value })}>
                    <option value="web_ui">UI 自动化</option>
                    <option value="api">接口/API</option>
                    <option value="pytest">pytest</option>
                    <option value="command">命令</option>
                    <option value="integration">集成</option>
                    <option value="functional">功能</option>
                    <option value="regression">回归</option>
                    <option value="security">安全</option>
                    <option value="manual">人工</option>
                  </select>
                  <select value={draftCase.priority ?? 'P2'} onChange={(event) => setDraftCase({ ...draftCase, priority: event.target.value })}>
                    <option value="P0">P0</option>
                    <option value="P1">P1</option>
                    <option value="P2">P2</option>
                    <option value="P3">P3</option>
                  </select>
                  <input
                    value={(draftCase.tags ?? []).join(',')}
                    onChange={(event) => setDraftCase({ ...draftCase, tags: event.target.value.split(',').map((tag) => tag.trim()).filter(Boolean) })}
                  />
                </div>
                <textarea value={draftCase.preconditions ?? ''} onChange={(event) => setDraftCase({ ...draftCase, preconditions: event.target.value })} />
                <textarea
                  className="steps-editor"
                  value={formatStepsForEditor(draftCase.steps ?? [])}
                  onChange={(event) =>
                    setDraftCase({
                      ...draftCase,
                      steps: parseStepsFromEditor(event.target.value),
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
                    <button className="ghost" onClick={() => runSingleCase(testCase)} disabled={testCase.status !== 'approved'}>
                      <Play size={15} />
                      单条执行
                    </button>
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
  openRunArtifact,
  diagnoseRunResult,
  saveDiagnosisKnowledge,
  applyDiagnosisSteps,
  loading,
  selectedProjectId,
  cases,
  environments,
  executorType,
  setExecutorType,
  environmentId,
  setEnvironmentId,
  headless,
  setHeadless,
  timeoutMs,
  setTimeoutMs,
  selectedCaseIds,
  setSelectedCaseIds,
}: {
  runs: TestRun[];
  ciTriggers: CiTrigger[];
  selectedRun?: TestRun;
  runApprovedCases: () => void;
  openRunDetail: (runId: number) => void;
  openRunArtifact: (artifact: RunArtifact) => void;
  diagnoseRunResult: (runId: number, resultId: number) => void;
  saveDiagnosisKnowledge: (runId: number, resultId: number) => void;
  applyDiagnosisSteps: (runId: number, result: RunResult) => void;
  loading: boolean;
  selectedProjectId?: number;
  cases: TestCase[];
  environments: ProjectEnvironment[];
  executorType: ExecutorType;
  setExecutorType: (value: ExecutorType) => void;
  environmentId?: number;
  setEnvironmentId: (value?: number) => void;
  headless: boolean;
  setHeadless: (value: boolean) => void;
  timeoutMs: number;
  setTimeoutMs: (value: number) => void;
  selectedCaseIds: number[];
  setSelectedCaseIds: (value: number[]) => void;
}) {
  const runnableCases = cases.filter((item) => isRunnableByExecutor(item, executorType));
  const runnableIds = runnableCases.map((item) => item.id);
  const validSelectedIds = selectedCaseIds.filter((id) => runnableIds.includes(id));
  const allSelected = runnableCases.length > 0 && validSelectedIds.length === runnableCases.length;

  function toggleRunCase(caseId: number) {
    setSelectedCaseIds(
      validSelectedIds.includes(caseId)
        ? validSelectedIds.filter((id) => id !== caseId)
        : [...validSelectedIds, caseId],
    );
  }

  return (
    <div className="two-column">
      <section className="panel">
        <PanelTitle icon={Play} title="测试执行" />
        <div className="run-config">
          <div className="segmented-control">
            <button className={executorType === 'mock' ? 'active' : ''} onClick={() => setExecutorType('mock')}>
              模拟
            </button>
            <button className={executorType === 'playwright' ? 'active' : ''} onClick={() => setExecutorType('playwright')}>
              Playwright
            </button>
            <button className={executorType === 'api' ? 'active' : ''} onClick={() => setExecutorType('api')}>
              API
            </button>
            <button className={executorType === 'pytest' ? 'active' : ''} onClick={() => setExecutorType('pytest')}>
              pytest
            </button>
            <button className={executorType === 'command' ? 'active' : ''} onClick={() => setExecutorType('command')}>
              命令
            </button>
          </div>
          <label>
            执行环境
            <select
              value={environmentId ?? ''}
              onChange={(event) => setEnvironmentId(event.target.value ? Number(event.target.value) : undefined)}
            >
              <option value="">默认环境</option>
              {environments.map((environment) => (
                <option key={environment.id} value={environment.id}>
                  {environment.name} · {environment.base_url}
                </option>
              ))}
            </select>
          </label>
          {executorType !== 'mock' && (
            <div className="executor-options">
              {executorType === 'playwright' && (
                <label className="checkbox-row">
                  <input type="checkbox" checked={headless} onChange={(event) => setHeadless(event.target.checked)} />
                  Headless
                </label>
              )}
              <label>
                {executorType === 'playwright' || executorType === 'api' ? '超时 ms' : '超时 ms'}
                <input
                  type="number"
                  min={1000}
                  step={1000}
                  value={timeoutMs}
                  onChange={(event) => setTimeoutMs(Number(event.target.value) || 30000)}
                />
              </label>
            </div>
          )}
          <div className="run-config-summary">
            <span>可执行用例</span>
            <strong>{validSelectedIds.length}/{runnableCases.length}</strong>
          </div>
        </div>
        <div className="run-case-picker">
          <div className="run-case-picker-header">
            <strong>选择执行用例</strong>
            <div>
              <button className="ghost" onClick={() => setSelectedCaseIds(runnableIds)} disabled={!runnableCases.length}>
                全选
              </button>
              <button className="ghost" onClick={() => setSelectedCaseIds([])} disabled={!validSelectedIds.length}>
                清空
              </button>
            </div>
          </div>
          {runnableCases.length === 0 ? (
            <p className="hint">暂无可由 {executorLabel(executorType)} 执行的已通过用例。</p>
          ) : (
            <div className="run-case-list">
              {runnableCases.map((testCase) => (
                <label className="run-case-option" key={testCase.id}>
                  <input
                    type="checkbox"
                    checked={validSelectedIds.includes(testCase.id)}
                    onChange={() => toggleRunCase(testCase.id)}
                  />
                  <span>
                    <strong>{testCase.title}</strong>
                    <small>#{testCase.id} · {testCase.priority} · {testCase.type}</small>
                  </span>
                </label>
              ))}
            </div>
          )}
          {allSelected && <p className="hint">已选择当前执行器可运行的全部用例。</p>}
        </div>
        <button className="run-button" onClick={runApprovedCases} disabled={!selectedProjectId || loading || !validSelectedIds.length}>
          <Play size={17} />
          执行选中用例
        </button>
        <div className="run-list">
          {runs.map((run) => (
            <article className="run-item" key={run.id}>
              <div>
                <strong>{run.name}</strong>
                <span className={`badge ${run.status}`}>{statusLabel[run.status] ?? run.status}</span>
              </div>
              <p>
                {run.executor_type} · 总数 {run.summary?.total ?? 0}，通过 {run.summary?.passed ?? 0}，失败 {run.summary?.failed ?? 0}
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
              <Detail label="执行器" value={selectedRun.executor_type} />
              <Detail label="环境" value={selectedRun.environment_id ? `#${selectedRun.environment_id}` : '默认'} />
              <Detail label="分支" value={selectedRun.branch ?? '-'} />
              <Detail label="提交" value={selectedRun.commit_sha ?? '-'} />
            </div>
            {selectedRun.error_message && <div className="notice">{selectedRun.error_message}</div>}
            {selectedRun.report && <pre>{selectedRun.report}</pre>}
            <PanelTitle icon={ShieldCheck} title="用例结果" />
            <div className="mini-list">
              {(selectedRun.results ?? []).map((result) => (
                <div className="knowledge-item" key={result.id}>
                  <strong>Case #{result.case_id ?? '-'} · {statusLabel[result.status] ?? result.status}</strong>
                  <p>{result.message}</p>
                  {result.artifacts.length > 0 && <p>附件：{result.artifacts.join('、')}</p>}
                  {result.status !== 'passed' && (
                    <button className="ghost primary" onClick={() => diagnoseRunResult(selectedRun.id, result.id)} disabled={loading}>
                      LLM 归因
                    </button>
                  )}
                  {result.ai_diagnosis?.root_cause && (
                    <FailureDiagnosisBox
                      diagnosis={result.ai_diagnosis}
                      disabled={loading}
                      onSave={() => saveDiagnosisKnowledge(selectedRun.id, result.id)}
                      onApplySteps={result.case_id ? () => applyDiagnosisSteps(selectedRun.id, result) : undefined}
                    />
                  )}
                  {result.logs && <pre>{result.logs}</pre>}
                </div>
              ))}
            </div>
            {(selectedRun.artifacts ?? []).length > 0 && (
              <>
                <PanelTitle icon={FileText} title="执行附件" />
                <div className="mini-list">
                  {(selectedRun.artifacts ?? []).map((artifact) => (
                    <div className="knowledge-item" key={artifact.id}>
                      <strong>{artifact.artifact_type} · {artifact.name}</strong>
                      <p>{artifact.path}</p>
                      <p className="artifact-url">{api.getRunArtifactUrl(artifact.run_id, artifact.id)}</p>
                      <p>{artifact.content_type ?? '未知类型'} · {artifact.size_bytes} bytes</p>
                      <div className="artifact-actions">
                        <button className="ghost primary" onClick={() => openRunArtifact(artifact)}>查看附件</button>
                        <button className="ghost" onClick={() => navigator.clipboard.writeText(api.getRunArtifactUrl(artifact.run_id, artifact.id))}>
                          复制地址
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
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

function FailureDiagnosisBox({
  diagnosis,
  disabled,
  onSave,
  onApplySteps,
}: {
  diagnosis: NonNullable<RunResult['ai_diagnosis']>;
  disabled: boolean;
  onSave: () => void;
  onApplySteps?: () => void;
  }) {
  const evidence = diagnosis.evidence ?? [];
  const suggestions = diagnosis.fix_suggestions ?? [];
  const suggestedSteps = diagnosis.suggested_steps ?? [];
  return (
    <div className="diagnosis-box">
      <div>
        <strong>失败归因</strong>
        <span>{diagnosis.failure_type ?? 'unknown'} · {diagnosis.confidence ?? 0} 分 · {diagnosis.diagnosed_by ?? 'diagnoser'}</span>
      </div>
      <p>{diagnosis.root_cause}</p>
      {evidence.length > 0 && (
        <ul>
          {evidence.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {suggestions.length > 0 && (
        <ol>
          {suggestions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      )}
      {suggestedSteps.length > 0 && (
        <div className="diagnosis-repair">
          <strong>建议修复步骤 JSON</strong>
          <pre>{JSON.stringify(suggestedSteps, null, 2)}</pre>
          {onApplySteps && (
            <button className="ghost primary" onClick={onApplySteps} disabled={disabled}>
              应用到用例
            </button>
          )}
        </div>
      )}
      <p>知识沉淀：{diagnosis.should_save_knowledge ? diagnosis.knowledge_type ?? 'execution_failure' : '暂不建议'}</p>
      {diagnosis.should_save_knowledge && (
        <button className="ghost primary" onClick={onSave} disabled={disabled}>
          沉淀知识
        </button>
      )}
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
  environmentVariables: string;
  setEnvironmentName: (value: string) => void;
  setEnvironmentUrl: (value: string) => void;
  setEnvironmentVariables: (value: string) => void;
  createEnvironment: () => void;
  deleteEnvironment: (environmentId: number) => void;
  refresh: () => void;
  selectedProjectId?: number;
}) {
  return (
    <section className="panel">
      <PanelTitle icon={Server} title="项目环境配置" />
      <div className="environment-grid">
        <div className="environment-form">
          <input value={props.environmentName} onChange={(event) => props.setEnvironmentName(event.target.value)} placeholder="环境名称" />
          <input value={props.environmentUrl} onChange={(event) => props.setEnvironmentUrl(event.target.value)} placeholder="Base URL" />
          <textarea
            className="environment-variables"
            value={props.environmentVariables}
            onChange={(event) => props.setEnvironmentVariables(event.target.value)}
            placeholder={'环境变量 JSON，例如：\n{\n  "SHOPXO_USERNAME": "huace_xm",\n  "SHOPXO_PASSWORD": "123456"\n}'}
          />
          <button className="wide-button" onClick={props.createEnvironment} disabled={!props.selectedProjectId}>保存环境</button>
        </div>
        <div className="mini-list">
          {props.environments.map((environment) => (
            <div className="mini-item" key={environment.id}>
              <div>
                <strong>{environment.name}</strong>
                <span>{environment.base_url}</span>
                {Object.keys(environment.variables || {}).length > 0 && (
                  <small>{Object.keys(environment.variables).join('、')}</small>
                )}
              </div>
              <button title="删除环境" onClick={() => props.deleteEnvironment(environment.id)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
