-- Dashboard Overview: portfolio content document (Dashboard Overview Plan.md). Additive only.
-- Apply in Supabase (`apply_migration` as "portfolio_content").
-- Mirrored by alembic/versions/007_portfolio_content.py.

-- 1. Activity type for portfolio saves.
alter type public.activity_type add value if not exists 'portfolio_updated';

-- 2. One row holds the whole main-page content document.
create table public.portfolio_content (
  id          smallint primary key default 1 check (id = 1),
  content     jsonb not null,
  version     integer not null default 1,
  updated_by  uuid references public.users(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger portfolio_content_set_updated_at
  before update on public.portfolio_content
  for each row execute function public.set_updated_at();

-- 3. No policies: only the backend reaches this table; the public read goes through the API.
alter table public.portfolio_content enable row level security;

-- 4. Seed with the text currently on the site.
insert into public.portfolio_content (id, content) values (1, $seed${
  "hero": {
    "eyebrow": "Agentic AI Expert @ IBM · 2026",
    "headline": "I build AI\nthat reasons.",
    "headline_accent": "And ships.",
    "intro": "Udit Narayana — full-stack engineer and agentic-AI specialist. I’ve sold it, operated it, and now I build it, end to end.",
    "highlights": [
      "Agentic AI",
      "Full-stack products",
      "Now at IBM"
    ],
    "currently_building": {
      "title": "Currently building Jerry",
      "subtitle": "A public AI assistant — live now",
      "url": null
    }
  },
  "about": {
    "statement": "Sales taught me to *listen*. Operations taught me to *deliver*. Engineering lets me do both — at scale.",
    "today": "Today I build *agentic AI*: systems that plan, retrieve, remember and act — and stay honest when they don’t know.",
    "stats": [
      {
        "id": "st1",
        "value": "4",
        "suffix": ".",
        "label": "roles across sales, ops and engineering"
      },
      {
        "id": "st2",
        "value": "40",
        "suffix": "%",
        "label": "less reporting time from ops dashboards at Flipkart"
      },
      {
        "id": "st3",
        "value": "1000",
        "suffix": "+",
        "label": "student conversations on career paths"
      },
      {
        "id": "st4",
        "value": "IBM",
        "suffix": "",
        "label": "Agentic AI Expert, since 2025"
      }
    ]
  },
  "what_i_do": {
    "title": "Curious full-stack engineer who wants AI to *actually work.*",
    "subtitle": "Agentic systems · Web products · APIs",
    "points": [
      {
        "id": "p1",
        "text": "Build *agentic AI systems* — LangGraph workflows with reasoning, tools, retrieval & persistent memory."
      },
      {
        "id": "p2",
        "text": "Ship *end-to-end web products* — React + Vite front ends on FastAPI & Postgres backends."
      },
      {
        "id": "p3",
        "text": "Design *clean, async APIs* other developers actually enjoy using."
      },
      {
        "id": "p4",
        "text": "Craft *micro-interactions and motion* that give products a sense of life."
      }
    ]
  },
  "skills": {
    "title": "What I’m fluent in.",
    "title_soft": "And how deep it runs.",
    "intro": "Pick a category. Bars show depth — the longer the bar, the more production miles."
  },
  "tech": [
    {
      "id": "t1",
      "name": "LangGraph",
      "logo_slug": "langchain",
      "categories": [
        "ai"
      ],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t2",
      "name": "RAG & pgvector",
      "logo_slug": null,
      "categories": [
        "ai"
      ],
      "level": "expert",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t3",
      "name": "Claude",
      "logo_slug": "claude",
      "categories": [
        "ai"
      ],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t4",
      "name": "Azure OpenAI",
      "logo_slug": null,
      "categories": [
        "ai"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t5",
      "name": "watsonx",
      "logo_slug": null,
      "categories": [
        "ai"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t6",
      "name": "Agent memory",
      "logo_slug": null,
      "categories": [
        "ai"
      ],
      "level": "advanced",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t7",
      "name": "Python",
      "logo_slug": "python",
      "categories": [
        "backend"
      ],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t8",
      "name": "FastAPI",
      "logo_slug": "fastapi",
      "categories": [
        "backend"
      ],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t9",
      "name": "PostgreSQL",
      "logo_slug": "postgresql",
      "categories": [
        "backend"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t10",
      "name": "Async API design",
      "logo_slug": null,
      "categories": [
        "backend"
      ],
      "level": "expert",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t11",
      "name": "Supabase",
      "logo_slug": "supabase",
      "categories": [
        "backend",
        "cloud"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t12",
      "name": "Docker",
      "logo_slug": "docker",
      "categories": [
        "backend",
        "cloud"
      ],
      "level": "working",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t13",
      "name": "TypeScript",
      "logo_slug": "typescript",
      "categories": [
        "frontend"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t14",
      "name": "React",
      "logo_slug": "react",
      "categories": [
        "frontend"
      ],
      "level": "expert",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": true
    },
    {
      "id": "t15",
      "name": "Vite",
      "logo_slug": "vite",
      "categories": [
        "frontend"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t16",
      "name": "Motion & CSS",
      "logo_slug": null,
      "categories": [
        "frontend"
      ],
      "level": "advanced",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t17",
      "name": "Azure",
      "logo_slug": null,
      "categories": [
        "cloud"
      ],
      "level": "working",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t18",
      "name": "CI/CD",
      "logo_slug": null,
      "categories": [
        "cloud"
      ],
      "level": "working",
      "show_in_strip": false,
      "show_in_what_i_do": false,
      "show_in_skills": true
    },
    {
      "id": "t19",
      "name": "pgvector",
      "logo_slug": "postgresql",
      "categories": [
        "backend"
      ],
      "level": "advanced",
      "show_in_strip": true,
      "show_in_what_i_do": true,
      "show_in_skills": false
    }
  ],
  "experience_section": {
    "title": "Sales floor to AI lab.",
    "title_soft": "An unusual route.",
    "intro": "It’s exactly why my agents solve business problems, not just benchmarks."
  },
  "experience": [
    {
      "id": "e1",
      "company": "IBM",
      "role": "Agentic AI Expert",
      "start_year": 2025,
      "end_year": null,
      "summary": "Designing multi-agent systems for enterprise clients on watsonx + LangGraph.",
      "highlights": [
        "Multi-agent orchestration for enterprise workflows",
        "RAG pipelines grounded in client data, with citations"
      ]
    },
    {
      "id": "e2",
      "company": "Neudesic",
      "role": "Agentic AI Expert",
      "start_year": 2024,
      "end_year": 2025,
      "summary": "Built agentic solutions for Azure-first enterprises at an IBM company.",
      "highlights": [
        "Shipped agent copilots on Azure OpenAI",
        "Turned fuzzy requirements into agent playbooks"
      ]
    },
    {
      "id": "e3",
      "company": "Flipkart",
      "role": "WAAS Operations Executive",
      "start_year": 2022,
      "end_year": 2024,
      "summary": "Ran warehouse-as-a-service operations at India’s largest e-commerce player.",
      "highlights": [
        "Streamlined vendor onboarding across hubs",
        "Built ops dashboards that cut reporting time 40%"
      ]
    },
    {
      "id": "e4",
      "company": "Skillvertex",
      "role": "Sales Executive",
      "start_year": 2021,
      "end_year": 2022,
      "summary": "Consultative edtech sales — where I learned to truly listen to users.",
      "highlights": [
        "Top-quartile conversion on advised cohorts",
        "1000+ student conversations on career paths"
      ]
    }
  ]
}$seed$::jsonb);
