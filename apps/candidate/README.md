# `apps/candidate`: RI Assessments magic-link UI

Next.js 15 App Router. Public app served at `assessments.revenueinstitute.com/a/{token}`. No sign-in UI; access is gated entirely by a signed magic-link JWT. Time, scoring, and submission are server-authoritative; the client only displays state pushed by FastAPI.

## Local development

```sh
bun --filter candidate dev    # http://localhost:3001
```

Requires the root `.env.local` and `bash scripts/link-env.sh`. To
exercise the candidate flow locally, seed a test assignment:

```sh
bun --filter api seed
```

which prints a `http://localhost:3001/a/<jwt>` URL.

## Magic-link flow

```
GET /a/{token}
  Server resolves the token via FastAPI GET /a/{token}/resolve
  Renders the consent gate with subject name, module title, time limit
POST /a/{token}/consent (server action -> FastAPI POST)
  Records consent + flips assignment to in_progress, returns deadline
  Redirects to /a/{token}/q/0
GET /a/{token}/q/{index}
  Loads the question, mounts the runner UI and integrity monitor
POST /a/{token}/q/{index}/submit
  Saves the raw answer, advances to the next question
POST /a/{token}/complete
  Marks completion, enqueues scoring, renders the /done page
```

The server is the source of truth for the deadline. The client timer
is a display only; submission endpoints reject expired sessions with
`409` regardless of what the client clock says.

## Integrity monitor (mount-once-at-root pattern)

The integrity client (`@repo/integrity/browser`) is mounted once at
the candidate `app/layout.tsx` root, not per question or per route.
Mounting it once means:

- A single document-level listener handles copy/cut/paste, contextmenu,
  fullscreenchange, visibilitychange, and the keyboard-shortcut
  block list, so routing between questions never re-arms duplicate
  handlers or drops events mid-transition.
- Events are batched and POSTed every 2 seconds to
  `/a/{token}/events`. Heartbeats every 10 seconds POST
  `/a/{token}/heartbeat` with focused-seconds-since-last; FastAPI
  accumulates into `attempts.active_time_seconds`.
- Code editors opt out of paste blocking by tagging the wrapper with
  `data-allow-paste="true"`. The integrity client distinguishes
  `paste_attempted` with `payload.allowed=true` from disallowed paste
  attempts so the admin event timeline can render them differently.
- Once the assignment is no longer `in_progress`, the heartbeat
  endpoint returns 200 no-op and the client stops the interval, so
  the `/done` page does not litter the console with retries.

## Question renderer dispatch

`packages/design-system` exports a `QuestionRenderer` that dispatches
on `question.type`:

| Type | Renderer |
|---|---|
| `mcq`, `multi_select` | Plain React radio / checkbox group. |
| `short_answer`, `long_answer` | Plain React input / textarea. |
| `code` | Monaco editor + Run / Run Visible Tests buttons + output panel. Run streams stdout/stderr live via the SSE `code/run?stream=true` endpoint; visible-tests stays buffered. |
| `sql` | Monaco (sql mode) + results grid. |
| `notebook` | Jupyter-lite iframe backed by an E2B kernel. |
| `n8n` | Iframe to a provisioned n8n workspace. |
| `diagram` | React Flow canvas with a question-specific node palette. |
| `scenario` | Multi-part branching shell that nests other renderers. |

Each renderer receives `{ attempt, onSubmit, onStateChange }` and
wires integrity events consistently via the shared monitor.

## SSE for code-run streaming

`POST /a/{token}/code/run` is an SSE endpoint. The candidate UI uses
the streaming `fetch` API (not `EventSource`, because the body must
be a POST with the code buffer):

```
event: started
data: {"language":"python","time_limit_ms":10000}

event: stdout
data: {"chunk":"hello\n"}

event: stderr
data: {"chunk":"warning: ...\n"}

event: result
data: {"exit_code":0,"duration_ms":421}
```

The backend bridges E2B's blocking `sandbox.process.start_and_wait`
to async via `code_runner.run_user_code_streaming`, which spawns the
execution on a worker thread and pushes stdout / stderr chunks onto
an asyncio queue. The router consumes the queue and yields SSE frames
without holding an open thread per request.

For batch (non-streaming) runs, the synchronous
`code_runner.run_user_code` returns a single `CodeRunResult` and is
used by `POST /a/{token}/code/test` and by the grader during scoring.

## Accessibility (WCAG 2.1 AA)

- The server-driven timer is rendered with an accessible name and
  live-region updates so screen readers announce remaining time.
- The consent gate uses semantic headings, a labeled checkbox, and
  a single primary button; tab order matches reading order.
- The question navigator is keyboard-navigable with visible focus
  rings and an `aria-current="step"` marker on the active question.
- Monaco is wrapped with a labeled region and an "exit editor" key
  hint so keyboard users can leave the editor focus trap.
- The diagram and n8n iframes are not keyboard-accessible in v1 (open
  spec item; see `CLAUDE.md`). Candidates that need keyboard-only
  access can request a non-interactive variant.

## Brand and layout

Dark-emerald brand system matches `revenueinstitute.com`. Single
column, generous reading width, timer pinned top-right, question
navigator collapsible on the left. Forward navigation only unless
the module config explicitly enables back-stepping.
