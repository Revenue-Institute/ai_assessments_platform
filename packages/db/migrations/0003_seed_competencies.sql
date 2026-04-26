-- 0003_seed_competencies.sql
-- Seed the competency taxonomy (spec §11.1).
-- Idempotent: safe to re-run when taxonomy.json is updated.
-- Source of truth: packages/competencies/src/taxonomy.json.

insert into competencies (id, domain, label, parent_id, description) values
  ('marketing', 'marketing', 'Marketing', null, 'Top-level marketing competency group'),
  ('marketing.strategy', 'marketing', 'Marketing Strategy', 'marketing', 'Brand positioning, ICP definition, go-to-market plans'),
  ('marketing.paid_ads', 'marketing', 'Paid Ads', 'marketing', 'Paid acquisition across channels'),
  ('marketing.paid_ads.google', 'marketing', 'Google Ads', 'marketing.paid_ads', 'Search, display, performance max'),
  ('marketing.paid_ads.linkedin', 'marketing', 'LinkedIn Ads', 'marketing.paid_ads', 'B2B paid social on LinkedIn'),
  ('marketing.seo', 'marketing', 'SEO', 'marketing', 'Organic search strategy and execution'),
  ('marketing.content', 'marketing', 'Content Marketing', 'marketing', 'Content planning, writing, distribution'),
  ('marketing.analytics', 'marketing', 'Marketing Analytics', 'marketing', 'Attribution, funnel analysis, reporting'),

  ('sales', 'sales', 'Sales', null, 'Top-level sales competency group'),
  ('sales.prospecting', 'sales', 'Prospecting', 'sales', 'Outbound research and outreach'),
  ('sales.discovery', 'sales', 'Discovery', 'sales', 'Pain identification and qualification'),
  ('sales.negotiation', 'sales', 'Negotiation', 'sales', 'Pricing, terms, and deal closure'),
  ('sales.pipeline_management', 'sales', 'Pipeline Management', 'sales', 'Forecasting, stage hygiene, deal review'),

  ('ops', 'ops', 'Operations', null, 'Top-level operations competency group'),
  ('ops.process_design', 'ops', 'Process Design', 'ops', 'Designing repeatable business processes'),
  ('ops.sop_documentation', 'ops', 'SOP Documentation', 'ops', 'Writing and maintaining standard operating procedures'),
  ('ops.project_management', 'ops', 'Project Management', 'ops', 'Scoping, scheduling, and delivering projects'),
  ('ops.vendor_management', 'ops', 'Vendor Management', 'ops', 'Selecting and managing third-party providers'),

  ('hubspot', 'hubspot', 'HubSpot', null, 'Top-level HubSpot competency group'),
  ('hubspot.workflows', 'hubspot', 'HubSpot Workflows', 'hubspot', 'Automation building inside HubSpot'),
  ('hubspot.integrations', 'hubspot', 'HubSpot Integrations', 'hubspot', 'Connecting HubSpot to external systems'),
  ('hubspot.migrations', 'hubspot', 'HubSpot Migrations', 'hubspot', 'Migrating data into and within HubSpot'),
  ('hubspot.reporting', 'hubspot', 'HubSpot Reporting', 'hubspot', 'Dashboards, reports, and custom report builder'),
  ('hubspot.crm_hygiene', 'hubspot', 'HubSpot CRM Hygiene', 'hubspot', 'Data quality, deduplication, property governance'),

  ('data', 'data', 'Data', null, 'Top-level data competency group'),
  ('data.sql', 'data', 'SQL', 'data', 'Querying relational databases'),
  ('data.python_analysis', 'data', 'Python Analysis', 'data', 'Pandas, numpy, exploratory analysis'),
  ('data.data_modeling', 'data', 'Data Modeling', 'data', 'Schema design, normalization, dimensional modeling'),
  ('data.visualization', 'data', 'Data Visualization', 'data', 'Building charts and dashboards that communicate'),
  ('data.stats', 'data', 'Statistics', 'data', 'Inferential statistics and experiment analysis'),
  ('data.data_science', 'data', 'Data Science', 'data', 'Applied ML, feature engineering, evaluation'),
  ('data.ml_basics', 'data', 'ML Basics', 'data', 'Foundational ML concepts and algorithms'),

  ('engineering', 'engineering', 'Engineering', null, 'Top-level engineering competency group'),
  ('engineering.python', 'engineering', 'Python', 'engineering', 'General-purpose Python engineering'),
  ('engineering.javascript_typescript', 'engineering', 'JavaScript / TypeScript', 'engineering', 'Web and Node engineering'),
  ('engineering.systems_design', 'engineering', 'Systems Design', 'engineering', 'Designing scalable, reliable systems'),
  ('engineering.debugging', 'engineering', 'Debugging', 'engineering', 'Diagnosing and resolving production issues'),

  ('ai', 'ai', 'AI', null, 'Top-level AI competency group'),
  ('ai.prompt_engineering', 'ai', 'Prompt Engineering', 'ai', 'Designing prompts for production LLM systems'),
  ('ai.rag', 'ai', 'Retrieval-Augmented Generation', 'ai', 'Embedding, retrieval, and grounding'),
  ('ai.agents', 'ai', 'AI Agents', 'ai', 'Tool-use, planning, and autonomous loops'),
  ('ai.evaluation', 'ai', 'AI Evaluation', 'ai', 'Eval design, regression detection, scoring rubrics'),
  ('ai.vertex', 'ai', 'Google Vertex AI', 'ai', 'Vertex AI platform and Gemini APIs'),
  ('ai.claude_anthropic', 'ai', 'Claude / Anthropic', 'ai', 'Claude API, tool use, prompt caching, agents'),

  ('automation', 'automation', 'Automation', null, 'Top-level automation competency group'),
  ('automation.n8n', 'automation', 'n8n', 'automation', 'Workflow automation in n8n'),
  ('automation.zapier', 'automation', 'Zapier', 'automation', 'Workflow automation in Zapier'),
  ('automation.make', 'automation', 'Make', 'automation', 'Workflow automation in Make (Integromat)'),
  ('automation.clay', 'automation', 'Clay', 'automation', 'Data enrichment and outbound automation in Clay'),

  ('finance', 'finance', 'Finance', null, 'Top-level finance competency group'),
  ('finance.budgeting', 'finance', 'Budgeting', 'finance', 'Annual and operational budget construction'),
  ('finance.financial_modeling', 'finance', 'Financial Modeling', 'finance', 'Three-statement and operating models'),
  ('finance.quickbooks', 'finance', 'QuickBooks', 'finance', 'Bookkeeping and reporting in QuickBooks')
on conflict (id) do update set
  domain = excluded.domain,
  label = excluded.label,
  parent_id = excluded.parent_id,
  description = excluded.description;
