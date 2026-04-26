# Revenue Institute Assessments Platform: V1 Build Spec

**Owner:** Stephen Lowisz, Revenue Institute **Purpose:** Internal custom-built assessments platform for pre-screening recruiting candidates and benchmarking the internal team. AI-generated assessments, interactive hands-on environments (code, n8n, notebooks, diagrams), randomized questions, AI scoring, longitudinal tracking. **Intended reader:** Claude Code / Antigravity agent implementing the v1 build.

---

## 1\. Goals and Scope

### 1.1 Primary goals

1. Internal users assign assessment modules to candidates or employees via magic-link URLs.  
2. AI generates complete assessment modules from a role description. No hand-authoring required.  
3. Questions are interactive where possible: real n8n workflow building, in-browser code execution, Jupyter notebooks, process diagrams.  
4. Every question is a **template** with typed variables and a deterministic solver. Questions randomize per attempt so answers cannot be copied.  
5. AI scores submissions against per-question rubrics, producing structured scores with rationale. Raw answers stored immutably.  
6. Time tracking is server-authoritative. Anti-cheat blocks copy/paste and logs integrity events (tab blur, fullscreen exit, paste attempts) into an integrity score.  
7. Same pipeline tests internal employees. Competency tagging, baseline/retest, cohort views, longitudinal dashboards.

### 1.2 Out of scope for v1

- Public marketing site (use existing revenueinstitute.com).  
- Payments / billing (internal tool).  
- Mobile apps.  
- Webcam proctoring (v2 consideration).  
- Third-party ATS integration (export CSV is enough for v1).

### 1.3 Success criteria

- An internal user can generate a complete 45-minute HubSpot Workflows assessment in under 5 minutes of work, review it, and assign it to a candidate.  
- The candidate receives a link, completes the assessment, and the admin sees scored results within 2 minutes of submission.  
- Retesting the same competency 30 days later with a randomized variant produces a comparable score.

---

## 2\. Tech Stack

| Layer | Choice | Rationale |
| :---- | :---- | :---- |
| Monorepo tooling | Turborepo \+ pnpm | Matches next-forge base. |
| Starter template | `vercel/next-forge` | Production Turborepo template. Apps \+ packages already wired. |
| Frontend framework | Next.js 15 (App Router) | Per next-forge. |
| UI components | shadcn/ui \+ Tailwind | Per next-forge. |
| Backend API | FastAPI (Python 3.12) | Matches Stephen's existing stack. Replaces next-forge `apps/api`. |
| Auth (admin) | Supabase Auth | Matches PIE spec. |
| Candidate auth | Signed JWT magic-link tokens | No account needed. |
| Database | Supabase (Postgres) with pgvector | Row-level security; pgvector for reference-library embeddings. |
| Object storage | Supabase Storage | Workflow exports, uploaded artifacts. |
| Job queue | BullMQ \+ Upstash Redis | Matches PIE spec. |
| Realtime | Server-Sent Events (SSE) | Matches PIE spec. Scoring progress, integrity event ack. |
| AI models | Claude Sonnet 4.5 (generation \+ scoring), Claude Haiku 4.5 (fast classification and event analysis) | Anthropic API direct. |
| Code execution sandbox | E2B | Fastest to integrate. Python/JS/SQL. |
| n8n runtime | Self-hosted n8n in Docker on Cloud Run or Fly.io | Per-attempt ephemeral workspaces. |
| Notebooks | E2B Jupyter kernels | Same sandbox provider as code. |
| Diagram editor | React Flow | For process-diagram questions. |
| Code editor | Monaco | In-browser code question runner. |
| Email delivery | Resend | Magic links, result notifications. |
| Deploy | Vercel (apps) \+ Cloud Run (FastAPI, n8n) | Keep FastAPI off Vercel Edge. |
| Observability | Sentry \+ Axiom | Error tracking and log ingestion. |

**Style rule throughout codebase:** no em dashes in any UI copy, emails, or generated content.

---

## 3\. Monorepo Structure

Fork `vercel/next-forge`, then restructure. Delete unused next-forge apps (docs, email can stay, web marketing app can go).

```
ri-assessments/
├── apps/
│   ├── admin/                   Next.js 15. Internal dashboard.
│   ├── candidate/               Next.js 15. Magic-link candidate UI.
│   └── api/                     FastAPI. Not deployed to Vercel.
├── packages/
│   ├── ui/                      shadcn components, question renderers, editors.
│   ├── schemas/                 Zod + generated Pydantic. The spine.
│   ├── db/                      Supabase schema, migrations, typed client.
│   ├── generator/               AI generation pipeline (intake, outline, generate).
│   ├── scoring/                 AI scoring service. Claude tool-use with rubrics.
│   ├── code-runner/             E2B wrapper. Code + notebook execution.
│   ├── n8n-runner/              n8n workspace provisioning + diff grading.
│   ├── diagram-runner/          React Flow integration + structural grading.
│   ├── randomizer/              Variable sampling + solver execution.
│   ├── integrity/               Anti-cheat event logger + scorer.
│   ├── modules/                 Seed module templates (versioned JSON).
│   ├── competencies/            Competency taxonomy definitions.
│   └── email/                   Resend templates (candidate invite, results).
├── infra/
│   ├── docker/                  Dockerfiles: api, n8n, workers.
│   ├── terraform/               Optional. Cloud Run, Supabase, Upstash.
│   └── scripts/                 Seed scripts, backup scripts.
├── turbo.json
├── pnpm-workspace.yaml
└── package.json
```

### 3.1 Package dependency rules

- `apps/*` may depend on any `packages/*`.  
- `packages/schemas` depends on nothing. It is the root.  
- `packages/db` depends only on `schemas`.  
- `packages/ui` depends on `schemas`.  
- Runner packages (`code-runner`, `n8n-runner`, `diagram-runner`, `randomizer`) depend only on `schemas`.  
- `packages/generator` and `packages/scoring` depend on `schemas` and are called from `apps/api`.  
- Never import from `apps/*` into `packages/*`.

---

## 4\. Core Data Model

Supabase Postgres. All tables have `id uuid pk default gen_random_uuid()`, `created_at timestamptz default now()`, `updated_at timestamptz`. All timestamps UTC. Row-level security enabled on every table.

### 4.1 Identity

```sql
-- Internal users (Supabase Auth manages this via auth.users; mirror key fields)
create table users (
  id uuid primary key references auth.users(id),
  email text not null unique,
  full_name text,
  role text not null check (role in ('admin','reviewer','viewer')),
  created_at timestamptz default now()
);

-- Subjects are anyone taking an assessment: candidates OR employees.
create table subjects (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('candidate','employee')),
  full_name text not null,
  email text not null,
  metadata jsonb default '{}'::jsonb,  -- role_applied_for, department, etc.
  created_at timestamptz default now(),
  unique (email, type)
);
```

### 4.2 Competencies

```sql
create table competencies (
  id text primary key,  -- e.g. 'hubspot.workflows'
  domain text not null,  -- 'hubspot', 'data', 'ops'
  label text not null,
  description text,
  parent_id text references competencies(id)
);
```

Seeded from `packages/competencies/taxonomy.json`. See Section 11\.

### 4.3 Modules and question templates

```sql
create table modules (
  id uuid primary key default gen_random_uuid(),
  slug text not null,
  title text not null,
  description text,
  domain text not null,
  target_duration_minutes int not null,
  difficulty text not null check (difficulty in ('junior','mid','senior','expert')),
  status text not null check (status in ('draft','published','archived')),
  version int not null default 1,
  created_by uuid references users(id),
  source_generation_id uuid,  -- links to generation_runs if AI-created
  created_at timestamptz default now(),
  published_at timestamptz,
  unique (slug, version)
);

create table question_templates (
  id uuid primary key default gen_random_uuid(),
  module_id uuid not null references modules(id) on delete cascade,
  position int not null,                   -- ordering within module
  type text not null,                      -- see schemas package: mcq, short, long, code, notebook, n8n, diagram, sql, scenario
  prompt_template text not null,           -- Jinja-style with ${var} placeholders
  variable_schema jsonb not null,          -- see Section 8.1
  solver_code text,                        -- Python source; runs in sandbox to compute expected answer
  solver_language text default 'python',
  interactive_config jsonb,                -- type-specific, see Section 7
  rubric jsonb not null,                   -- see Section 9.2
  competency_tags text[] not null default '{}',
  time_limit_seconds int,                  -- per-question soft limit
  max_points numeric(6,2) not null default 10,
  metadata jsonb default '{}'::jsonb
);

create index on question_templates(module_id, position);
```

### 4.4 Assignments and attempts

```sql
create table assignments (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  module_snapshot jsonb not null,   -- full frozen module+questions at assignment time
  module_id uuid references modules(id), -- soft link for reporting
  created_by uuid not null references users(id),
  token_hash text not null,         -- hash of the JWT sent to candidate
  expires_at timestamptz not null,
  status text not null check (status in ('pending','in_progress','completed','expired','cancelled')) default 'pending',
  started_at timestamptz,
  completed_at timestamptz,
  random_seed bigint not null,      -- used to sample variables
  total_time_seconds int,
  integrity_score numeric(5,2),
  final_score numeric(6,2),
  max_possible_score numeric(6,2),
  created_at timestamptz default now()
);

create table attempts (
  id uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references assignments(id) on delete cascade,
  question_template_id uuid not null references question_templates(id),
  rendered_prompt text not null,            -- post-interpolation text shown to candidate
  variables_used jsonb not null,            -- the sampled values
  expected_answer jsonb,                    -- solver output, immutable
  raw_answer jsonb,                         -- candidate submission
  interactive_artifact_url text,            -- pointer to storage (n8n JSON, notebook ipynb)
  started_at timestamptz,
  submitted_at timestamptz,
  active_time_seconds int,                  -- sum of focused intervals
  score numeric(6,2),
  max_score numeric(6,2) not null,
  score_rationale text,
  scorer_model text,
  scorer_version text,
  rubric_version text,
  created_at timestamptz default now(),
  unique (assignment_id, question_template_id)
);
```

### 4.5 Events (integrity \+ timing)

```sql
create table attempt_events (
  id bigserial primary key,
  attempt_id uuid not null references attempts(id) on delete cascade,
  assignment_id uuid not null references assignments(id) on delete cascade,
  event_type text not null,     -- see Section 10.3 taxonomy
  payload jsonb default '{}'::jsonb,
  client_timestamp timestamptz,
  server_timestamp timestamptz not null default now(),
  user_agent text,
  ip_hash text
);

create index on attempt_events(assignment_id, server_timestamp);
create index on attempt_events(attempt_id);
```

### 4.6 AI generation history

```sql
create table generation_runs (
  id uuid primary key default gen_random_uuid(),
  created_by uuid references users(id),
  stage text not null check (stage in ('outline','full','single_question','revision')),
  input_brief jsonb not null,
  output jsonb not null,
  model text not null,
  tokens_in int,
  tokens_out int,
  latency_ms int,
  status text not null check (status in ('pending','success','failed')),
  error text,
  parent_run_id uuid references generation_runs(id),
  created_at timestamptz default now()
);

create table reference_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  source_url text,
  content text,
  uploaded_by uuid references users(id),
  domain text,
  created_at timestamptz default now()
);

create table reference_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references reference_documents(id) on delete cascade,
  content text not null,
  embedding vector(1536),            -- pgvector; use Voyage-3 or OpenAI text-embedding-3-small
  position int not null
);

create index on reference_chunks using hnsw (embedding vector_cosine_ops);
```

### 4.7 Assessment series (benchmarking and retest)

```sql
create table assessment_series (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  name text not null,                -- 'HubSpot Workflows competency'
  competency_focus text[] not null,
  cadence_days int,                  -- null = ad-hoc
  next_due_at timestamptz,
  created_at timestamptz default now()
);

create table series_assignments (
  series_id uuid not null references assessment_series(id) on delete cascade,
  assignment_id uuid not null references assignments(id) on delete cascade,
  sequence_number int not null,
  primary key (series_id, assignment_id)
);

-- Materialized view for fast competency scoring (rebuilt on attempt completion)
create table competency_scores (
  id uuid primary key default gen_random_uuid(),
  subject_id uuid not null references subjects(id),
  competency_id text not null references competencies(id),
  assignment_id uuid not null references assignments(id),
  score_pct numeric(5,2) not null,
  point_total numeric(6,2) not null,
  point_possible numeric(6,2) not null,
  computed_at timestamptz default now()
);

create index on competency_scores(subject_id, competency_id, computed_at desc);
```

---

## 5\. Schemas Package (the spine)

`packages/schemas` is the single source of truth for shared data shapes. TypeScript (Zod) is canonical. Pydantic models are generated from Zod via a build step using `zod-to-json-schema` \+ `datamodel-code-generator`. The generated Pydantic lives at `apps/api/src/generated/schemas/` and is gitignored with a pre-commit hook that regenerates.

### 5.1 Question type discriminated union

```ts
// packages/schemas/src/question.ts
import { z } from 'zod';

export const QuestionTypeEnum = z.enum([
  'mcq',            // multiple choice, single answer
  'multi_select',   // multiple choice, multiple answers
  'short_answer',   // single-line text or number
  'long_answer',    // paragraph, rubric-graded
  'code',           // Monaco + E2B execution
  'notebook',       // Jupyter via E2B
  'sql',            // SQL against seeded DuckDB
  'n8n',            // n8n workflow build or fix
  'diagram',        // React Flow process diagram
  'scenario',       // multi-part branching scenario
]);

export const VariableSpec = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('int'), min: z.number(), max: z.number(), step: z.number().default(1) }),
  z.object({ kind: z.literal('float'), min: z.number(), max: z.number(), decimals: z.number().default(2) }),
  z.object({ kind: z.literal('choice'), options: z.array(z.string()).min(2) }),
  z.object({ kind: z.literal('dataset'), pool: z.array(z.string()).min(1) }),
  z.object({ kind: z.literal('string_template'), pattern: z.string() }),
]);

export const VariableSchema = z.record(z.string(), VariableSpec);

export const Rubric = z.object({
  version: z.string().default('1'),
  criteria: z.array(z.object({
    id: z.string(),
    label: z.string(),
    weight: z.number().min(0).max(1),
    description: z.string(),
    scoring_guidance: z.string(),
  })),
  scoring_mode: z.enum(['exact_match', 'numeric_tolerance', 'structural_match', 'rubric_ai', 'test_cases']),
  tolerance: z.number().optional(),
  test_cases: z.array(z.any()).optional(),
});

export const QuestionTemplate = z.object({
  id: z.string().uuid().optional(),
  type: QuestionTypeEnum,
  prompt_template: z.string(),
  variable_schema: VariableSchema,
  solver_code: z.string().optional(),           // Python source
  interactive_config: z.any().optional(),       // see Section 7
  rubric: Rubric,
  competency_tags: z.array(z.string()),
  time_limit_seconds: z.number().optional(),
  max_points: z.number().default(10),
  difficulty: z.enum(['junior','mid','senior','expert']),
});

export const Module = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  domain: z.string(),
  target_duration_minutes: z.number(),
  difficulty: z.enum(['junior','mid','senior','expert']),
  questions: z.array(QuestionTemplate),
});
```

### 5.2 Interactive config per question type

```ts
// packages/schemas/src/interactive.ts
export const CodeConfig = z.object({
  language: z.enum(['python','javascript','typescript','sql','bash']),
  starter_code: z.string(),
  hidden_tests: z.string(),                // pytest-style or JS test source
  visible_tests: z.string().optional(),
  allow_internet: z.boolean().default(false),
  packages: z.array(z.string()).default([]),
  time_limit_exec_ms: z.number().default(10000),
});

export const N8nConfig = z.object({
  mode: z.enum(['build','fix']),
  starter_workflow: z.any(),                // exported n8n JSON
  reference_workflow: z.any(),              // used for grading; never sent to candidate
  required_nodes: z.array(z.string()),      // node types that must appear
  required_connections: z.array(z.object({ from: z.string(), to: z.string() })),
  test_payloads: z.array(z.any()),          // inputs piped to the workflow for execution comparison
  credentials_provided: z.array(z.string()),
});

export const NotebookConfig = z.object({
  starter_notebook: z.any(),                // .ipynb JSON
  dataset_urls: z.array(z.string()),
  validation_script: z.string(),            // runs against submission kernel state
  required_outputs: z.array(z.string()),
});

export const DiagramConfig = z.object({
  mode: z.enum(['build','analyze']),
  starter_nodes: z.array(z.any()),
  reference_structure: z.any(),
  grading_mode: z.enum(['structural','ai_narrative','both']),
});

export const SqlConfig = z.object({
  schema_sql: z.string(),
  seed_sql: z.string(),
  expected_query_result: z.any().optional(),
  expected_sql_patterns: z.array(z.string()).optional(),
});
```

### 5.3 Integrity event taxonomy

```ts
// packages/schemas/src/integrity.ts
export const IntegrityEventType = z.enum([
  'attempt_started',
  'question_served',
  'focus_gained',
  'focus_lost',
  'visibility_hidden',
  'visibility_visible',
  'fullscreen_entered',
  'fullscreen_exited',
  'copy_attempted',
  'cut_attempted',
  'paste_attempted',
  'context_menu_opened',
  'keyboard_shortcut_blocked',   // payload: { keys }
  'window_resized',
  'devtools_opened',             // heuristic, best-effort
  'network_offline',
  'network_online',
  'interactive_state_saved',
  'code_executed',
  'test_run',
  'n8n_workflow_saved',
  'notebook_cell_run',
  'question_submitted',
  'attempt_submitted',
]);
```

### 5.4 Generation brief (AI input)

```ts
// packages/schemas/src/generation.ts
export const GenerationBrief = z.object({
  role_title: z.string(),
  responsibilities: z.string(),              // paste from JD
  target_duration_minutes: z.number(),
  difficulty: z.enum(['junior','mid','senior','expert']),
  domains: z.array(z.string()),
  question_mix: z.object({
    mcq_pct: z.number(),
    short_pct: z.number(),
    long_pct: z.number(),
    code_pct: z.number(),
    interactive_pct: z.number(),             // n8n, notebook, diagram, sql
  }),
  reference_document_ids: z.array(z.string().uuid()).default([]),
  required_competencies: z.array(z.string()),
  notes: z.string().optional(),
});

export const GeneratedOutline = z.object({
  title: z.string(),
  description: z.string(),
  topics: z.array(z.object({
    name: z.string(),
    competency_tags: z.array(z.string()),
    weight_pct: z.number(),
    question_count: z.number(),
    recommended_types: z.array(z.string()),
    rationale: z.string(),
  })),
  total_points: z.number(),
  estimated_duration_minutes: z.number(),
});
```

---

## 6\. AI Generation System

`packages/generator`. Three stages. Each stage is a separate Claude tool call. Every stage persists to `generation_runs`.

### 6.1 Flow

```
Admin fills GenerationBrief form
    → POST /api/generator/outline           (Stage 1: Claude Sonnet 4.5)
        → returns GeneratedOutline draft
    → Admin reviews, edits inline, approves
    → POST /api/generator/questions         (Stage 2: parallel per-topic)
        → fan-out: one Claude call per topic, each returns QuestionTemplate[]
        → merge + validate against Zod schema
    → Admin reviews in UI, can:
        * regenerate single question (POST /api/generator/question/{id}/revise)
        * preview 5 randomized variants (POST /api/generator/preview-variants)
        * edit any field in place
    → Click Publish → module.status = 'published', version frozen
```

### 6.2 Outline prompt (stage 1\)

Lives at `packages/generator/prompts/outline.md`. Key directives:

- Analyze the responsibilities text. Extract concrete skills, tools, and decision scenarios.  
- Propose 4 to 8 topics covering the role with weights summing to 100\.  
- For each topic pick 1 to 2 recommended question types biased toward interactive where the skill is practical (n8n for automation, code for engineering, notebook for data science, sql for analysts, diagram for process work).  
- Respect the question mix percentages in the brief within \+/- 10%.  
- Never invent competency tags. Only use tags present in `packages/competencies/taxonomy.json` (list injected into prompt as context).  
- Estimate time per question type (mcq=45s, short=2min, long=5min, code=8min, notebook=12min, n8n=15min, diagram=8min) and confirm total stays within target\_duration\_minutes \+/- 15%.  
- Output as structured tool call matching `GeneratedOutline` schema.

### 6.3 Question generation prompt (stage 2\)

Lives at `packages/generator/prompts/questions.md`. Runs once per topic. Returns array of `QuestionTemplate` objects for that topic.

Per-question generation rules for the prompt:

1. **Always emit a template, not a static question.** Every scenario includes variables.  
2. **Variable schema must be typed and constrained.** No free-form variables.  
3. **Solver must be deterministic Python.** For code/sql questions, solver returns test cases parameterized by the variables. For numeric questions, solver computes the exact answer. For long\_answer, solver returns `None` and scoring\_mode is `rubric_ai`.  
4. **Rubric must be detailed enough to score without the original question author.** Include scoring\_guidance that names common wrong-answer patterns.  
5. **Every question gets competency\_tags from the taxonomy.**  
6. **Interactive questions get full `interactive_config` matching their type schema.**  
7. **n8n starter and reference workflows must be valid exported n8n JSON.** Agent uses n8n docs injected into context to produce them. Must include credentials stubs, not real credentials.  
8. **Code hidden\_tests use pytest for Python, vitest for JS/TS.** Must pass against the solver's computed expected answer across all sampled variable values.  
9. **Prompts never contain em dashes.** Use commas or parentheses.  
10. **Self-verification step:** after drafting, regenerate the solver's expected output for 3 sampled variable sets and confirm the hidden tests pass. If not, revise before emitting.

### 6.4 Reference library retrieval

When `reference_document_ids` is populated in the brief, the generator retrieves top-k chunks (k=10 per topic) by cosine similarity against the topic name \+ competency tags as the query. Chunks are injected into the prompt under `<reference_material>` tags. Citations back to document titles are included in the generated question's `metadata.sources`.

Reference docs can be uploaded as markdown, pdf, or URL. PDF extraction via `pypdf`. URL extraction via `trafilatura`. Chunked at 800 tokens with 100 token overlap. Embedded via Voyage `voyage-3` (1024 dims) or OpenAI `text-embedding-3-small` (1536 dims). Store whichever is used in `reference_chunks.embedding`; keep dimension consistent per deployment.

### 6.5 Revision endpoint

`POST /api/generator/question/{id}/revise` accepts:

```json
{ "instruction": "make this harder and use a Fortune 500 context", "preserve": ["competency_tags","type"] }
```

Sends the current question \+ instruction to Claude Sonnet 4.5, returns a new draft which replaces the existing question\_template in-place (but preserves id and fields listed in `preserve`). Creates a new row in `generation_runs` with `stage='revision'` and `parent_run_id` pointing at the original.

### 6.6 Variant preview endpoint

`POST /api/generator/preview-variants` takes a question\_template\_id, samples 5 independent variable sets (random seeds 1..5), renders the prompt and expected answer for each. Displayed side-by-side in UI so admin can confirm the template produces fair, unambiguous questions across the distribution.

---

## 7\. Interactive Runners

Each runner package exports the same interface:

```ts
// packages/schemas/src/runner.ts
export interface InteractiveRunner<TConfig, TState, TArtifact> {
  provision(attemptId: string, config: TConfig, variables: Record<string,any>): Promise<ProvisionResult>;
  loadState(attemptId: string): Promise<TState>;
  saveState(attemptId: string, state: TState): Promise<void>;
  submit(attemptId: string): Promise<TArtifact>;
  grade(artifact: TArtifact, config: TConfig, rubric: Rubric, variables: Record<string,any>): Promise<GradeResult>;
  teardown(attemptId: string): Promise<void>;
}

export interface ProvisionResult {
  embed_url?: string;          // for iframe-based runners (n8n)
  session_token?: string;      // scoped auth to the ephemeral env
  initial_state: any;
}

export interface GradeResult {
  score: number;
  max_score: number;
  rationale: string;
  breakdown: Array<{ criterion_id: string; score: number; max: number; note: string }>;
}
```

### 7.1 Code runner (E2B)

`packages/code-runner`.

**Provision:** create E2B sandbox via `@e2b/code-interpreter`. Install packages from `config.packages`. Write starter code to `/home/user/solution.{ext}`. Write hidden tests to `/home/user/tests/`. Return sandbox id as session\_token.

**Candidate UI:** Monaco editor (via `@monaco-editor/react`) mounted in candidate app. "Run" button executes their current buffer in the sandbox; stdout/stderr streamed back via SSE. "Run Visible Tests" runs only `visible_tests`. Hidden tests never exposed.

**Submit:** save buffer to attempt.raw\_answer.code. Save execution history to attempt\_artifact\_url (signed Supabase Storage URL).

**Grade:** execute hidden tests in a fresh sandbox with candidate's code. Parameterize tests with the same variables used in the rendered prompt. Score \= (passing tests / total tests) \* max\_points. For code-quality criteria in the rubric, run a Claude Sonnet 4.5 pass on the final code with the rubric.

**Teardown:** kill sandbox. E2B auto-kills after timeout, but be explicit.

### 7.2 n8n runner

`packages/n8n-runner`.

**Infrastructure:** self-hosted n8n behind an API gateway. Multi-tenant mode using n8n's user-management API. Cloud Run service with 1 instance per \~20 concurrent attempts. Persistent volume for workflow storage.

**Provision flow:**

1. Call n8n REST API `POST /users` to create ephemeral user `attempt-{attempt_id}@internal`.  
2. Auth as that user, `POST /workflows` with the `config.starter_workflow`.  
3. Create the stubbed credentials listed in `config.credentials_provided` (mock HTTP, mock database).  
4. Generate a short-lived n8n JWT scoped to that user.  
5. Return `embed_url = ${N8N_HOST}/workflow/{id}?auth=${jwt}` and session\_token.

**Candidate UI:** full n8n editor in an iframe. Anti-cheat wrapper in the parent page still runs. The iframe origin is locked to n8n host; clipboard blocking is applied at the parent level. Candidate builds/fixes the workflow.

**Submit:**

1. Call `GET /workflows/{id}` to export their final workflow JSON.  
2. Call `POST /workflows/{id}/execute` with each payload in `config.test_payloads`; capture execution JSON.  
3. Save both to Supabase Storage. attempt.interactive\_artifact\_url points to the export.

**Grade (structural \+ behavioral):**

- Structural score: normalize both workflows (strip positions, ids). Compare node types, parameters, and connection graph against `reference_workflow`. Use `packages/n8n-runner/src/diff.ts` which produces a per-criterion breakdown.  
- Behavioral score: compare execution outputs to reference execution outputs. Use deep equality with tolerance for timestamps and uuids.  
- Narrative rubric pass: Claude Sonnet 4.5 reviews the candidate's workflow JSON against the rubric for style criteria (error handling, node naming, expression quality).  
- Weighted combine per rubric criteria.

**Teardown:** delete ephemeral user. Workflow cascades delete.

### 7.3 Notebook runner (E2B Jupyter)

`packages/code-runner` (same package, different adapter).

**Provision:** spawn E2B sandbox with jupyter kernel. Upload `starter_notebook.ipynb`. Download dataset URLs into sandbox `/data/`.

**Candidate UI:** render notebook with `@nteract/core` or an iframe to a jupyter-lite instance backed by the E2B kernel. Cell execution round-trips through our API to the sandbox.

**Submit:** export final .ipynb (with outputs) to storage.

**Grade:** run `config.validation_script` in the sandbox against the final kernel state. Validation script returns JSON `{ pass: bool, details: {...} }`. Combined with Claude rubric pass on the narrative cells.

### 7.4 Diagram runner

`packages/diagram-runner`.

**UI:** React Flow canvas. Palette of node types specific to the question (process steps, decisions, data stores, roles). Candidate drags, connects, labels.

**Submit:** export React Flow JSON (nodes \+ edges).

**Grade:**

- Structural mode: graph isomorphism check against `reference_structure` with fuzzy node-label matching.  
- AI narrative mode: Claude reviews the structure \+ candidate's written rationale against rubric.

### 7.5 SQL runner

`packages/code-runner` (sql adapter).

**Provision:** spin a DuckDB in-memory instance inside an E2B sandbox. Apply `schema_sql` and `seed_sql`.

**UI:** Monaco with SQL syntax mode \+ results grid.

**Grade:** execute candidate query, compare result set to `expected_query_result` with column-order-agnostic match. If `expected_sql_patterns` is set, also grep candidate's SQL for pattern compliance (e.g., must use window function).

---

## 8\. Randomization Engine

`packages/randomizer`.

### 8.1 Variable sampling

At assignment creation, the API calls `sampleVariables(variableSchema, seed=assignmentId)`:

```ts
export function sampleVariables(
  schema: VariableSchema,
  seed: string | number
): Record<string, any> {
  const rng = seedrandom(String(seed));
  const result: Record<string, any> = {};
  for (const [name, spec] of Object.entries(schema)) {
    switch (spec.kind) {
      case 'int':
        result[name] = Math.floor(rng() * ((spec.max - spec.min) / spec.step + 1)) * spec.step + spec.min;
        break;
      case 'float':
        result[name] = +(rng() * (spec.max - spec.min) + spec.min).toFixed(spec.decimals);
        break;
      case 'choice':
        result[name] = spec.options[Math.floor(rng() * spec.options.length)];
        break;
      case 'dataset':
        result[name] = spec.pool[Math.floor(rng() * spec.pool.length)];
        break;
      case 'string_template':
        result[name] = renderStringPattern(spec.pattern, rng);
        break;
    }
  }
  return result;
}
```

Seeded RNG makes rendering reproducible. Store the seed on the assignment.

### 8.2 Prompt rendering

Jinja-style interpolation via `nunjucks`. The template:

```
A SaaS company has $${{ revenue | number }} ARR and is growing {{ growth_rate * 100 }}% YoY.
Forecast their ARR in {{ years }} years assuming constant growth.
```

With variables `{revenue: 12000000, growth_rate: 0.22, years: 3}` renders to a concrete question.

### 8.3 Solver execution

Solvers are Python. Executed in an E2B sandbox at assignment creation time (solver is trusted: generated by AI, reviewed by admin, sandboxed regardless):

```py
# solver_code pattern
def solve(variables: dict) -> dict:
    revenue = variables['revenue']
    rate = variables['growth_rate']
    years = variables['years']
    final = revenue * ((1 + rate) ** years)
    return {
        'expected_answer': round(final, 2),
        'tolerance': 0.01,
    }
```

The return shape varies by question type. For code questions, returns `{test_cases: [...]}`. For scenarios, returns `{rubric_context: {...}}` injected into the grading prompt.

Solver results cached on the attempt row. Never recomputed post-hoc.

### 8.4 Fairness validation

The preview-variants endpoint (Section 6.6) lets admins see 5 renderings. In addition, a background check runs at publish time: sample 50 variable sets, confirm the solver produces outputs that satisfy a simple sanity rubric ("answer is a finite number", "test cases run green against the reference solution if provided"). Fails block publish.

---

## 9\. Scoring System

`packages/scoring`. Triggered when assignment status flips to `completed`.

### 9.1 Scoring orchestrator

BullMQ job `score-assignment`. For each attempt in the assignment:

1. Look up the question\_template and rubric.  
2. Route based on `rubric.scoring_mode`:  
   - `exact_match`: string/number equality with expected\_answer.  
   - `numeric_tolerance`: abs difference within tolerance.  
   - `structural_match`: call runner's `grade` function (n8n, diagram).  
   - `test_cases`: call runner's `grade` function (code, sql, notebook).  
   - `rubric_ai`: send to Claude Sonnet 4.5 with rubric \+ answer.  
3. Persist score, rationale, scorer\_model, scorer\_version, rubric\_version.  
4. Emit SSE event to admin dashboard.

After all attempts scored, compute:

- `final_score = sum(attempt.score)`  
- `max_possible_score = sum(attempt.max_score)`  
- Competency rollup: group attempts by competency\_tags, compute weighted pct, upsert into `competency_scores`.

### 9.2 Rubric AI scoring

Claude Sonnet 4.5 call with a strict tool schema:

```json
{
  "name": "submit_score",
  "input_schema": {
    "type": "object",
    "properties": {
      "breakdown": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "criterion_id": {"type": "string"},
            "score": {"type": "number"},
            "max": {"type": "number"},
            "note": {"type": "string"}
          },
          "required": ["criterion_id","score","max","note"]
        }
      },
      "overall_rationale": {"type": "string"},
      "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["breakdown","overall_rationale","confidence"]
  }
}
```

System prompt includes:

- The rendered question (with variables filled in).  
- The expected answer from solver.  
- The candidate's raw answer.  
- The full rubric JSON.  
- Explicit instruction to score each criterion separately, cite evidence from the answer, and flag low confidence.

Score below confidence threshold (0.6) auto-flags for human review on admin dashboard.

### 9.3 Retry and re-scoring

Every attempt stores `scorer_model` and `scorer_version` and `rubric_version`. An admin-only endpoint `POST /api/attempts/{id}/rescore` triggers re-evaluation, keeping the old row in `attempt_scores_history` (audit table, same shape as attempt scoring fields). Raw answers are immutable. Scores are versioned.

---

## 10\. Time Tracking and Anti-Cheat

`packages/integrity`.

### 10.1 Time tracking

Server-authoritative. Timer on candidate UI is a display driven by server-pushed deadlines. Key endpoints:

- `POST /api/attempts/{id}/start` → server records `started_at = now()` and returns `server_deadline = started_at + time_limit` for display.  
- Client every 10 seconds POSTs `/api/attempts/{id}/heartbeat` with focused\_seconds\_since\_last. Server accumulates into `active_time_seconds`.  
- Any client-side clock manipulation cannot shift the server deadline.

Module-level time limit enforced at `POST /api/assignments/{id}/submit-question` (rejects with 409 if past deadline).

### 10.2 Anti-cheat event handling

Client-side library in `packages/integrity/browser.ts`. Mounted at the root of the candidate app:

```ts
export function installIntegrityMonitor(attemptId: string, send: (event: IntegrityEvent) => void) {
  // Visibility
  document.addEventListener('visibilitychange', () => {
    send({ type: document.hidden ? 'visibility_hidden' : 'visibility_visible' });
  });

  // Focus
  window.addEventListener('blur', () => send({ type: 'focus_lost' }));
  window.addEventListener('focus', () => send({ type: 'focus_gained' }));

  // Copy / cut / paste
  ['copy','cut','paste'].forEach(evt => {
    document.addEventListener(evt, (e) => {
      // Allow paste in explicitly marked code editors (data-allow-paste="true")
      const target = e.target as HTMLElement;
      if (target?.closest('[data-allow-paste="true"]')) {
        send({ type: `${evt}_attempted`, payload: { allowed: true } });
        return;
      }
      e.preventDefault();
      send({ type: `${evt}_attempted`, payload: { allowed: false } });
    });
  });

  // Context menu
  document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    send({ type: 'context_menu_opened' });
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    const blockedCombos = [
      { key: 'c', meta: true }, { key: 'v', meta: true }, { key: 'x', meta: true },
      { key: 'c', ctrl: true }, { key: 'v', ctrl: true }, { key: 'x', ctrl: true },
      { key: 'u', meta: true }, { key: 's', meta: true }, { key: 'p', meta: true },
    ];
    const matches = blockedCombos.some(c =>
      e.key.toLowerCase() === c.key && ((c.meta && e.metaKey) || (c.ctrl && e.ctrlKey))
    );
    const outsideCodeEditor = !(e.target as HTMLElement)?.closest('[data-allow-paste="true"]');
    if (matches && outsideCodeEditor) {
      e.preventDefault();
      send({ type: 'keyboard_shortcut_blocked', payload: { key: e.key, meta: e.metaKey, ctrl: e.ctrlKey } });
    }
  });

  // Fullscreen
  document.addEventListener('fullscreenchange', () => {
    send({ type: document.fullscreenElement ? 'fullscreen_entered' : 'fullscreen_exited' });
  });

  // Resize (window shrink heuristic for split-screen)
  let lastW = window.innerWidth;
  window.addEventListener('resize', () => {
    if (window.innerWidth < lastW * 0.7) send({ type: 'window_resized', payload: { from: lastW, to: window.innerWidth } });
    lastW = window.innerWidth;
  });

  // Network
  window.addEventListener('online', () => send({ type: 'network_online' }));
  window.addEventListener('offline', () => send({ type: 'network_offline' }));

  // DevTools heuristic (not reliable, best-effort, no false alarms)
  const threshold = 160;
  setInterval(() => {
    if (window.outerWidth - window.innerWidth > threshold || window.outerHeight - window.innerHeight > threshold) {
      send({ type: 'devtools_opened' });
    }
  }, 2000);
}
```

Events batched and POSTed every 2 seconds to `/api/attempts/{id}/events`. Server writes to `attempt_events`.

### 10.3 Fullscreen enforcement

Assessment session requires fullscreen. On `fullscreen_exited` outside the first 3 seconds, the UI shows a modal "Return to fullscreen to continue. Exits are logged." Timer continues to run. No auto-kick on v1.

### 10.4 Integrity score computation

At assignment completion, a worker computes `integrity_score` (0 to 100, higher is cleaner):

```
base = 100
- visibility_hidden events > 3: subtract 3 each beyond
- focus_lost > 5: subtract 2 each beyond
- fullscreen_exited: subtract 8 each
- paste_attempted (disallowed): subtract 5 each
- copy_attempted: subtract 2 each
- devtools_opened: subtract 15 (flag hard)
- window_resized (shrink): subtract 3 each
- total active_time_seconds < 30% of total_time_seconds: subtract 20 (suspiciously fast)
Floor at 0.
```

Stored on assignment. Displayed in admin UI with color coding: 85+ green, 60-84 yellow, \<60 red. Never auto-rejects.

### 10.5 Consent gate

Before timer starts, candidate sees a page listing everything being monitored, time limit, and fullscreen requirement. Must click "I understand and consent to begin." Consent timestamp \+ hashed IP stored on assignment row.

---

## 11\. Benchmarking and Longitudinal Tracking

### 11.1 Competency taxonomy

`packages/competencies/taxonomy.json`. Hierarchical. V1 seed covers:

```
marketing.*
  marketing.strategy
  marketing.paid_ads.google
  marketing.paid_ads.linkedin
  marketing.seo
  marketing.content
  marketing.analytics

sales.*
  sales.prospecting
  sales.discovery
  sales.negotiation
  sales.pipeline_management

ops.*
  ops.process_design
  ops.sop_documentation
  ops.project_management
  ops.vendor_management

hubspot.*
  hubspot.workflows
  hubspot.integrations
  hubspot.migrations
  hubspot.reporting
  hubspot.crm_hygiene

data.*
  data.sql
  data.python_analysis
  data.data_modeling
  data.visualization
  data.stats
  data.data_science
  data.ml_basics

engineering.*
  engineering.python
  engineering.javascript_typescript
  engineering.systems_design
  engineering.debugging

ai.*
  ai.prompt_engineering
  ai.rag
  ai.agents
  ai.evaluation
  ai.vertex                   # Google Vertex AI
  ai.claude_anthropic

automation.*
  automation.n8n
  automation.zapier
  automation.make
  automation.clay

finance.*
  finance.budgeting
  finance.financial_modeling
  finance.quickbooks
```

All question\_templates must tag at least one competency. Validated at publish.

### 11.2 Cohort and subject dashboards

**Subject detail page (`/admin/subjects/{id}`):**

- Radar chart across all competencies with data.  
- Trend lines per competency over time (from `competency_scores` history).  
- Assignment history table.  
- Delta badges on retests ("+12% vs last attempt").

**Cohort dashboard (`/admin/cohorts`):**

- Filter by type (candidate/employee), domain, role, date range.  
- Heatmap: subjects (rows) x competencies (cols).  
- Team averages.  
- Peer percentile per subject per competency.  
- "Weak spot detection": competencies where team median is below configurable threshold.

### 11.3 Candidate-vs-team overlay

On a candidate's results page, their score per competency is plotted with the internal employee distribution (box plot or violin). Admin sees at a glance "is this candidate above/below our bench at each skill."

### 11.4 Retest and series

Admin creates an `assessment_series` for a subject:

- Pick competencies of focus.  
- Pick cadence (30/60/90 days or manual).  
- System auto-creates assignments on schedule using randomized variants of templates tagged with those competencies.  
- Notification email sent at `next_due_at`.  
- Series page shows trend of each competency across sequence\_number.

### 11.5 Training-loop hook (v1.1, wire but not populate)

`competency_scores` table has a trigger-style read: on score save, if pct \< 60 and subject.type \= 'employee', insert a suggestion row into `training_suggestions` (table with subject\_id, competency\_id, suggested\_at, linked\_resource\_url, dismissed\_at). UI shows these in a panel but v1 doesn't auto-populate with SOP/ClickUp links. That's v1.1.

---

## 12\. Admin App Features

`apps/admin`. Next.js 15 App Router. Supabase Auth for sign-in. Role-gated routes.

### 12.1 Routes

```
/                               Dashboard: recent assignments, pending reviews, integrity flags
/modules                        Module library list
/modules/new                    Generation wizard (Section 6.1)
/modules/{id}                   Module editor (questions, rubrics, variants preview)
/modules/{id}/preview           Candidate preview (as a candidate would see)
/subjects                       List candidates + employees
/subjects/{id}                  Subject detail with competency radar and history
/assignments                    All assignments table, filters
/assignments/new                Bulk-assign flow: pick module, pick subjects, set expiry
/assignments/{id}               Assignment detail: per-question results, integrity events timeline, rescore button
/cohorts                        Cohort analytics
/series                         Assessment series management
/references                     Reference library (upload, search)
/competencies                   Read-only view of taxonomy
/settings/users                 Manage internal users and roles
/settings/api                   API keys for integrations (future)
```

### 12.2 Generation wizard UX

Multi-step wizard on `/modules/new`:

1. Brief form (GenerationBrief fields).  
2. Loading screen while outline generates. Show model \+ tokens used. Typically 10-20s.  
3. Outline review: editable. Drag to reorder topics. Edit weights. Edit question counts.  
4. Click "Generate questions." Parallel fan-out. Progress per topic (1 of 5... 2 of 5...).  
5. Module editor opens with all questions. Each question has: edit in place, regenerate, preview variants, delete, add new.  
6. Publish button enables when all questions pass Zod validation and fairness check.

### 12.3 Integrity events timeline

On `/assignments/{id}`, render events as a time-series with icons per event type. Hover for payload. Filter by type. Linked to per-question segments.

---

## 13\. Candidate App Features

`apps/candidate`. Next.js 15 App Router. No auth UI; access only via magic-link token.

### 13.1 Flow

```
GET /a/{token}
  → server validates token signature + expiry
  → hydrate assignment, subject
  → render consent screen
POST /a/{token}/consent
  → records consent + starts assignment.status = 'in_progress'
  → redirects to first question
GET /a/{token}/q/{index}
  → loads question, starts server timer for that attempt
  → mounts integrity monitor
  → mounts appropriate runner UI
POST /a/{token}/q/{index}/submit
  → saves raw answer, moves to next question
After last question:
  → POST /a/{token}/complete
  → shows "Thanks. You will hear back from our team."
  → triggers scoring job
```

### 13.2 Question renderer (UI)

`packages/ui/src/question-renderer/` dispatches on `question.type`:

- `MCQRenderer`, `ShortAnswerRenderer`, `LongAnswerRenderer`: plain React.  
- `CodeRenderer`: Monaco \+ run button \+ output panel \+ test results.  
- `NotebookRenderer`: jupyter-lite iframe.  
- `N8nRenderer`: iframe to provisioned n8n workspace.  
- `DiagramRenderer`: React Flow canvas.  
- `SqlRenderer`: Monaco (sql mode) \+ results grid.

All renderers receive `{ attempt, onSubmit, onStateChange }` and wire integrity events consistently.

### 13.3 Style

Dark-emerald brand system matches revenueinstitute.com. Clean, minimal, distraction-free. Single-column reading width. Timer in top-right. Question navigator in a collapsible side panel (only forward navigation allowed unless module config says otherwise).

---

## 14\. API Endpoints (FastAPI)

Base: `apps/api`. OpenAPI generated. All endpoints return JSON. Auth via Supabase JWT for admin endpoints, signed token for candidate endpoints.

### 14.1 Admin endpoints (JWT auth)

```
POST   /api/generator/outline              Stage 1 generation
POST   /api/generator/questions            Stage 2 generation
POST   /api/generator/question/{id}/revise Revise single question
POST   /api/generator/preview-variants     5-variant preview

GET    /api/modules
POST   /api/modules
GET    /api/modules/{id}
PATCH  /api/modules/{id}
POST   /api/modules/{id}/publish
POST   /api/modules/{id}/archive

POST   /api/modules/{id}/questions
PATCH  /api/modules/{id}/questions/{qid}
DELETE /api/modules/{id}/questions/{qid}

GET    /api/subjects
POST   /api/subjects
GET    /api/subjects/{id}
GET    /api/subjects/{id}/competency-scores

POST   /api/assignments                    Create single or bulk
GET    /api/assignments
GET    /api/assignments/{id}
POST   /api/assignments/{id}/cancel
POST   /api/assignments/{id}/resend-email

GET    /api/attempts/{id}
POST   /api/attempts/{id}/rescore

GET    /api/cohorts/heatmap?filters...
GET    /api/cohorts/weak-spots?filters...

POST   /api/series
GET    /api/series
GET    /api/series/{id}

POST   /api/references                     Upload document
GET    /api/references
DELETE /api/references/{id}

GET    /api/competencies
```

### 14.2 Candidate endpoints (signed token auth)

```
GET    /a/{token}                          Resolves to HTML app shell
POST   /a/{token}/consent
POST   /a/{token}/start
GET    /a/{token}/questions/{index}
POST   /a/{token}/questions/{index}/save   Save interim state (state persistence)
POST   /a/{token}/questions/{index}/submit
POST   /a/{token}/events                   Batched integrity events
POST   /a/{token}/heartbeat
POST   /a/{token}/complete
```

### 14.3 Interactive runner endpoints (token auth, scoped to attempt)

```
POST   /a/{token}/code/run                 Execute code in E2B, stream stdout via SSE
POST   /a/{token}/code/test                Run visible tests
POST   /a/{token}/notebook/run-cell
POST   /a/{token}/notebook/save
GET    /a/{token}/n8n/embed                Returns n8n embed URL (signed)
POST   /a/{token}/n8n/export               Grab current workflow state
POST   /a/{token}/sql/query
POST   /a/{token}/diagram/save
```

### 14.4 Webhooks

```
POST   /webhooks/resend                    Bounce/spam tracking
POST   /webhooks/scoring-complete          Internal, from worker to admin SSE channel
```

---

## 15\. Third-Party Services

| Service | Purpose | Setup notes |
| :---- | :---- | :---- |
| Anthropic API | Claude Sonnet 4.5 (generation, scoring), Claude Haiku 4.5 (event classification) | Single workspace. Separate API keys for generation vs scoring for cost attribution. |
| Supabase | Postgres \+ Auth \+ Storage \+ pgvector | Enable pgvector extension. Configure RLS policies per Section 4 notes. |
| Upstash Redis | BullMQ backing store | REST API variant works with serverless. |
| E2B | Code \+ notebook \+ sql sandboxes | Purchase paid plan for production quotas. |
| Resend | Transactional email | SPF/DKIM set on revenueinstitute.com subdomain. |
| Voyage AI (or OpenAI) | Embeddings for reference library | Pick one; keep dimensions consistent. |
| Sentry | Error tracking | One project per app (admin, candidate, api). |
| Axiom | Log aggregation | Stream from FastAPI \+ Vercel. |
| n8n (self-hosted) | Interactive workflow assessments | Run on Cloud Run with persistent volume for workflow storage. |
| Vercel | Deploy admin \+ candidate | Use Vercel Remote Cache with Turborepo. |
| Cloud Run (or Fly.io) | Deploy FastAPI \+ n8n \+ workers | FastAPI \+ separate worker service consuming BullMQ. |

---

## 16\. Environment Variables

```
# Shared
NODE_ENV
APP_ENV                              # local | staging | production

# Supabase
SUPABASE_URL
SUPABASE_ANON_KEY                    # candidate app only
SUPABASE_SERVICE_ROLE_KEY            # api + admin server
DATABASE_URL                         # direct pg connection for FastAPI

# Auth
JWT_SIGNING_SECRET                   # for candidate magic links
SESSION_COOKIE_SECRET

# Anthropic
ANTHROPIC_API_KEY_GENERATION
ANTHROPIC_API_KEY_SCORING

# E2B
E2B_API_KEY

# n8n
N8N_HOST
N8N_ADMIN_API_KEY
N8N_WEBHOOK_SECRET

# Redis
UPSTASH_REDIS_URL
UPSTASH_REDIS_TOKEN

# Email
RESEND_API_KEY
RESEND_FROM_EMAIL                    # assessments@revenueinstitute.com

# Embeddings
VOYAGE_API_KEY                       # or OPENAI_API_KEY
EMBEDDING_MODEL                      # voyage-3 | text-embedding-3-small
EMBEDDING_DIMS                       # 1024 | 1536

# Observability
SENTRY_DSN_ADMIN
SENTRY_DSN_CANDIDATE
SENTRY_DSN_API
AXIOM_TOKEN
AXIOM_DATASET

# Storage
SUPABASE_STORAGE_BUCKET_ARTIFACTS    # stores workflow exports, notebooks
SUPABASE_STORAGE_BUCKET_REFERENCES   # stores uploaded reference docs

# App URLs
NEXT_PUBLIC_ADMIN_URL
NEXT_PUBLIC_CANDIDATE_URL
INTERNAL_API_URL
```

---

## 17\. Build Order for V1

Sequence de-risks the hardest parts first. Each phase should be fully working and deployable before moving on.

**Phase 0: Foundation (week 1\)**

1. Fork `vercel/next-forge`. Delete unused apps. Add `apps/candidate` and `apps/api`.  
2. Wire Supabase, run migrations for Section 4 tables.  
3. Ship `packages/schemas` complete with Section 5 types. Add Pydantic generation.  
4. Ship `packages/db` typed client.  
5. Seed competency taxonomy.  
6. Stand up deploy pipelines: Vercel for admin/candidate, Cloud Run for api.

**Phase 1: The critical path (weeks 2-3)**

1. `packages/randomizer` with seeded variable sampling \+ solver executor (E2B-backed).  
2. Code runner (E2B) end-to-end: provision, Monaco UI, run, submit, grade with hidden tests.  
3. Bare question renderer for mcq, short\_answer, long\_answer, code.  
4. Candidate magic-link flow \+ consent \+ integrity monitor \+ heartbeat.  
5. Admin auth \+ minimal module editor (CRUD without AI generation yet).  
6. Manually seed one module with 5 questions (mix of mcq \+ code). End-to-end test: create assignment, take it, get scored.

**Phase 2: AI generation (week 4\)**

1. `packages/generator` outline stage.  
2. Generation wizard UI (admin).  
3. Question generation stage with variable schemas \+ solvers.  
4. Preview-variants endpoint.  
5. Reference library upload \+ embedding \+ retrieval.  
6. Revision endpoint.

**Phase 3: AI scoring \+ interactive expansion (weeks 5-6)**

1. `packages/scoring` orchestrator \+ Claude tool-use scoring \+ SSE.  
2. Rescore \+ history audit.  
3. n8n runner (self-hosted n8n \+ workspace provisioning \+ diff grading). Longest integration. Start here in parallel with scoring if resources allow.  
4. SQL runner.  
5. Notebook runner.  
6. Diagram runner.

**Phase 4: Benchmarking (week 7\)**

1. Competency score rollups.  
2. Subject detail page \+ radar.  
3. Cohort heatmap.  
4. Candidate-vs-team overlay.  
5. Assessment series (create, schedule, email).

**Phase 5: Polish and harden (week 8\)**

1. Integrity score computation \+ admin surfacing.  
2. Bulk assignment flow.  
3. Resend email reliability \+ templates.  
4. Sentry \+ Axiom wired on all services.  
5. Load test: 50 concurrent candidates across mix of interactive types.  
6. Seed 10 real modules via the generator (HubSpot, n8n, Vertex, Python data, ops process, marketing strategy, etc.).

**V1 complete.** Ship to internal team for first benchmark round before using on external candidates.

---

## 18\. Non-Functional Requirements

- **Latency:** candidate question load \< 2s p95. Code run \< 5s p95 for trivial code. n8n workspace provision \< 8s p95.  
- **Concurrency:** 50 simultaneous candidates with interactive sessions.  
- **Data retention:** raw answers retained indefinitely. Integrity events retained 12 months.  
- **Backups:** Supabase daily \+ point-in-time. Storage bucket versioning on.  
- **Security:** RLS on all subject-scoped tables. Candidate tokens signed \+ short-lived (default 7 days from assignment). IPs hashed not stored raw. No PII in logs.  
- **Audit:** every score change written to `attempt_scores_history`. Every module publish snapshot persisted. Every generation run retained.  
- **Accessibility:** candidate app WCAG 2.1 AA minimum. Screen-reader labels on all renderers. Keyboard nav for everything except diagram/n8n interactive canvases.

---

## 19\. Open Decisions to Confirm Before Build

1. **Embedding provider:** Voyage vs OpenAI. Voyage-3 is cheaper and competitive for retrieval; OpenAI is more ops-familiar. Default Voyage-3 unless you prefer otherwise.  
2. **n8n license:** self-hosted n8n community edition vs Enterprise. Community covers v1 needs. Move to Enterprise only if you need SSO/multi-tenancy features beyond what the API provides.  
3. **Sandbox provider:** E2B now, revisit at \~$500/mo run-rate whether to migrate interactive code to self-hosted Judge0 or Daytona. Interface is abstracted in `packages/code-runner` so swap is contained.  
4. **Proctoring v2:** webcam \+ screen recording decision. Flag for post-v1 once you have data on actual cheat attempts.  
5. **Candidate app domain:** `assessments.revenueinstitute.com` vs separate brand. Recommend same domain for trust.

---

## 20\. Deliverables Checklist

When v1 is done:

- [ ] All migrations applied in Supabase  
- [ ] All 10 seed modules published via generator  
- [ ] 5 internal employees benchmarked on their primary competencies  
- [ ] 3 candidate assessments completed end-to-end  
- [ ] Admin dashboard shows integrity events, scores, rationale  
- [ ] Rescore endpoint works without data loss  
- [ ] All interactive runners provisioning under 10s p95  
- [ ] Load test passes with 50 concurrent  
- [ ] Runbook for n8n cluster operations  
- [ ] Runbook for rescoring and reference-library updates

