import os
import uuid
import json
import logging
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Optional
from datetime import datetime

from .db_backend import Connection, create_backend


logger = logging.getLogger("emo_ai.db")


class SecurityError(Exception):
    """Base exception for security violations in the database layer."""

class InvalidColumnError(SecurityError):
    """Raised when an unwhitelisted column name is used in a dynamic query."""


# Per-table whitelists for dynamic UPDATE SET clauses.
# Each frozenset defines the ONLY column names allowed in UPDATE ... SET {fields}.
ALLOWED_TASK_COLUMNS = frozenset({
    "status", "result", "error", "progress", "message", "agent", "tool_used",
    "project_id", "session_id", "mission_id", "mode",
})
ALLOWED_AGENT_COLUMNS = frozenset({
    "name", "display_name", "role", "description", "icon", "color", "status",
    "model_binding", "tools", "memory", "execution_policy", "system_prompt",
    "last_run_at", "task_count", "success_count", "error_count", "tools_used",
})
ALLOWED_PROJECT_COLUMNS = frozenset({
    "name", "description", "path", "is_active", "is_archived",
})
ALLOWED_SESSION_COLUMNS = frozenset({
    "name", "is_active", "is_archived",
})
ALLOWED_CONVERSATION_COLUMNS = frozenset({
    "name", "is_active", "is_archived",
})


DB_PATH = os.getenv("EMO_DB_PATH", "emo_ai.db")

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_sessions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT NOT NULL DEFAULT 'جلسة جديدة',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id),
    session_id    TEXT REFERENCES project_sessions(id),
    user_id       TEXT REFERENCES users(id),
    name          TEXT NOT NULL DEFAULT 'محادثة جديدة',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content       TEXT NOT NULL,
    file_name     TEXT,
    file_type     TEXT,
    file_size     INTEGER,
    file_base64   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    session_id    TEXT REFERENCES project_sessions(id),
    project_id    TEXT REFERENCES projects(id),
    message       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'complete', 'error')),
    result        TEXT,
    error         TEXT,
    agent         TEXT,
    tool_used     TEXT,
    progress      INTEGER NOT NULL DEFAULT 0,
    mission_id    TEXT,
    mode          TEXT DEFAULT 'manual',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT REFERENCES users(id),
    action        TEXT NOT NULL,
    resource      TEXT,
    details       TEXT,
    ip_address    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(is_archived);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON project_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON project_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_archived ON project_sessions(is_archived);
CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS provider_keys (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    provider              TEXT NOT NULL,
    key_value             TEXT NOT NULL,
    nickname              TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'untested'
                          CHECK (status IN ('untested','valid','invalid','error')),
    last_test_at          TEXT,
    last_test_latency_ms  INTEGER,
    last_test_error       TEXT,
    models_cache_json     TEXT,
    models_cached_at      TEXT,
    is_active             INTEGER NOT NULL DEFAULT 0,
    is_enabled            INTEGER NOT NULL DEFAULT 1,
    sort_order            INTEGER NOT NULL DEFAULT 0,
    rotation_index        INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_provider_keys_provider ON provider_keys(provider);
CREATE INDEX IF NOT EXISTS idx_provider_keys_active ON provider_keys(provider, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_keys_nickname
    ON provider_keys(provider, nickname) WHERE is_enabled = 1;

-- v1.1 Phase 3: Agent Control Center
CREATE TABLE IF NOT EXISTS agents (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    icon          TEXT DEFAULT 'fa-robot',
    color         TEXT DEFAULT 'var(--emo-blue-light)',
    status        TEXT NOT NULL DEFAULT 'online'
                  CHECK (status IN ('online', 'busy', 'learning', 'error', 'disabled')),
    -- model_binding stored as JSON
    model_binding TEXT NOT NULL DEFAULT '{}',
    -- tools list stored as JSON array
    tools         TEXT NOT NULL DEFAULT '[]',
    -- memory {type, scope} as JSON
    memory        TEXT NOT NULL DEFAULT '{}',
    -- execution_policy {mode, permissions, timeout, max_tokens} as JSON
    execution_policy TEXT NOT NULL DEFAULT '{}',
    -- system prompt
    system_prompt TEXT DEFAULT '',
    -- health metrics
    last_run_at   TEXT,
    task_count    INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    error_count   INTEGER NOT NULL DEFAULT 0,
    tools_used    TEXT NOT NULL DEFAULT '[]',
    is_built_in   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);

-- v1.1 Phase 4: Autonomous Mission Controller
CREATE TABLE IF NOT EXISTS missions (
    id            TEXT PRIMARY KEY,
    goal          TEXT NOT NULL,
    intent        TEXT NOT NULL DEFAULT '{}',
    plan          TEXT NOT NULL DEFAULT '[]',
    agents        TEXT NOT NULL DEFAULT '[]',
    tools         TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','running','validating','recovering','completed','failed','cancelled')),
    current_step  INTEGER NOT NULL DEFAULT 0,
    progress      TEXT NOT NULL DEFAULT '{}',
    errors        TEXT NOT NULL DEFAULT '[]',
    validation    TEXT NOT NULL DEFAULT '[]',
    result        TEXT NOT NULL DEFAULT '{}',
    project_id    TEXT,
    conversation_id TEXT,
    execution_log TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    started_at    TEXT,
    completed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at);
CREATE INDEX IF NOT EXISTS idx_missions_project_id ON missions(project_id);
CREATE INDEX IF NOT EXISTS idx_missions_conversation_id ON missions(conversation_id);

-- v1.1 Phase 5: Industrial Control Plane
CREATE TABLE IF NOT EXISTS enterprise_orgs (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    sector              TEXT NOT NULL DEFAULT 'enterprise_it',
    region              TEXT NOT NULL DEFAULT 'global',
    compliance_profile  TEXT NOT NULL DEFAULT 'none',
    policy_id           TEXT NOT NULL DEFAULT 'default',
    deployment_profile  TEXT NOT NULL DEFAULT 'development',
    status              TEXT NOT NULL DEFAULT 'active',
    config              TEXT NOT NULL DEFAULT '{}',
    metadata            TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ent_orgs_sector ON enterprise_orgs(sector);
CREATE INDEX IF NOT EXISTS idx_ent_orgs_status ON enterprise_orgs(status);

CREATE TABLE IF NOT EXISTS enterprise_users (
    id              TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'viewer',
    status          TEXT NOT NULL DEFAULT 'invited',
    mfa_enabled     INTEGER NOT NULL DEFAULT 0,
    department      TEXT NOT NULL DEFAULT '',
    scopes          TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at   TEXT,
    UNIQUE(email, organization_id)
);
CREATE INDEX IF NOT EXISTS idx_ent_users_org ON enterprise_users(organization_id);
CREATE INDEX IF NOT EXISTS idx_ent_users_role ON enterprise_users(role);

CREATE TABLE IF NOT EXISTS enterprise_policies (
    id                       TEXT PRIMARY KEY,
    name                     TEXT NOT NULL,
    organization_id          TEXT NOT NULL,
    description              TEXT NOT NULL DEFAULT '',
    allowed_tools            TEXT NOT NULL DEFAULT '',
    blocked_tools            TEXT NOT NULL DEFAULT '',
    approval_required_for    TEXT NOT NULL DEFAULT '',
    max_timeout_s            INTEGER NOT NULL DEFAULT 60,
    max_memory_mb            INTEGER NOT NULL DEFAULT 256,
    max_calls_per_mission    INTEGER NOT NULL DEFAULT 100,
    max_concurrent_missions  INTEGER NOT NULL DEFAULT 5,
    require_mfa_for          TEXT NOT NULL DEFAULT '',
    deny_after_hours         INTEGER NOT NULL DEFAULT 0,
    allowed_hours            TEXT NOT NULL DEFAULT '{}',
    active                   INTEGER NOT NULL DEFAULT 1,
    metadata                 TEXT NOT NULL DEFAULT '{}',
    created_at               TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ent_policies_org ON enterprise_policies(organization_id);

CREATE TABLE IF NOT EXISTS enterprise_audit (
    id           TEXT PRIMARY KEY,
    action       TEXT NOT NULL,
    who          TEXT NOT NULL DEFAULT 'system',
    user_email   TEXT NOT NULL DEFAULT '',
    user_role    TEXT NOT NULL DEFAULT '',
    org_id       TEXT NOT NULL DEFAULT '',
    agent_id     TEXT NOT NULL DEFAULT '',
    tool         TEXT NOT NULL DEFAULT '',
    subject      TEXT NOT NULL DEFAULT '',
    result       TEXT NOT NULL DEFAULT 'ok',
    approval_id  TEXT NOT NULL DEFAULT '',
    severity     TEXT NOT NULL DEFAULT 'LOW',
    deployment   TEXT NOT NULL DEFAULT 'development',
    context      TEXT NOT NULL DEFAULT '{}',
    ts           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ent_audit_action ON enterprise_audit(action);
CREATE INDEX IF NOT EXISTS idx_ent_audit_who ON enterprise_audit(who);
CREATE INDEX IF NOT EXISTS idx_ent_audit_org ON enterprise_audit(org_id);
CREATE INDEX IF NOT EXISTS idx_ent_audit_ts ON enterprise_audit(ts);
CREATE INDEX IF NOT EXISTS idx_ent_audit_severity ON enterprise_audit(severity);

-- ══════════════════════════════════════════════════════════════════════════════
-- SKILLS TABLE (RC12.4 — Skill Evolution Layer)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS skills (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    version             TEXT NOT NULL DEFAULT '1.0.0',
    owner_agent         TEXT NOT NULL DEFAULT '',
    category            TEXT NOT NULL DEFAULT 'general',
    required_tools      TEXT NOT NULL DEFAULT '[]',
    required_models     TEXT NOT NULL DEFAULT '[]',
    required_permissions TEXT NOT NULL DEFAULT '[]',
    input_schema        TEXT NOT NULL DEFAULT '{}',
    output_schema       TEXT NOT NULL DEFAULT '{}',
    success_rate        REAL NOT NULL DEFAULT 0.0,
    failure_rate        REAL NOT NULL DEFAULT 0.0,
    usage_count         INTEGER NOT NULL DEFAULT 0,
    avg_execution_time  REAL NOT NULL DEFAULT 0.0,
    best_agent          TEXT NOT NULL DEFAULT '',
    best_model          TEXT NOT NULL DEFAULT '',
    created_from_mission TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'discovered'
                        CHECK (status IN ('discovered','proposed','validating','approved','active','optimized','deprecated')),
    approval_state      TEXT NOT NULL DEFAULT 'pending'
                        CHECK (approval_state IN ('pending','approved','rejected')),
    approval_by         TEXT NOT NULL DEFAULT '',
    approval_at         TEXT,
    metadata            TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_owner ON skills(owner_agent);
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
CREATE INDEX IF NOT EXISTS idx_skills_approval ON skills(approval_state);
CREATE INDEX IF NOT EXISTS idx_skills_created ON skills(created_at);

-- ══════════════════════════════════════════════════════════════════════════════
-- SKILL EXECUTION HISTORY (RC12.4.1 — separated from skills row)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS skill_execution_history (
    id              TEXT PRIMARY KEY,
    skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    mission_id      TEXT NOT NULL DEFAULT '',
    agent_id        TEXT NOT NULL DEFAULT '',
    success         INTEGER NOT NULL DEFAULT 1,
    duration        REAL NOT NULL DEFAULT 0.0,
    cost            REAL NOT NULL DEFAULT 0.0,
    error           TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_seh_skill ON skill_execution_history(skill_id);
CREATE INDEX IF NOT EXISTS idx_seh_mission ON skill_execution_history(mission_id);
CREATE INDEX IF NOT EXISTS idx_seh_created ON skill_execution_history(created_at);

-- ══════════════════════════════════════════════════════════════════════════════
-- SKILL VERSIONS (RC12.4.1 — immutable version history)
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS skill_versions (
    id              TEXT PRIMARY KEY,
    skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    config          TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT NOT NULL DEFAULT '',
    approved_by     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sv_skill ON skill_versions(skill_id);
CREATE INDEX IF NOT EXISTS idx_sv_version ON skill_versions(skill_id, version);

-- ══════════════════════════════════════════════════════════════════════════════
-- UNIFIED IDENTITY & RBAC (RC12.5 Phase 1)
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS identity_roles (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    level           INTEGER NOT NULL DEFAULT 0,
    description     TEXT NOT NULL DEFAULT '',
    can_approve     INTEGER NOT NULL DEFAULT 0,
    can_deploy      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS identity_permissions (
    id              TEXT PRIMARY KEY,
    resource        TEXT NOT NULL,
    action          TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'own',
    require_approval INTEGER NOT NULL DEFAULT 0,
    require_mfa     INTEGER NOT NULL DEFAULT 0,
    UNIQUE(resource, action, scope)
);

CREATE TABLE IF NOT EXISTS identity_role_permissions (
    role_id         TEXT NOT NULL REFERENCES identity_roles(id) ON DELETE CASCADE,
    permission_id   TEXT NOT NULL REFERENCES identity_permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS identity_user_roles (
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         TEXT NOT NULL REFERENCES identity_roles(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL DEFAULT '',
    org_id          TEXT NOT NULL DEFAULT '',
    assigned_at     TEXT NOT NULL DEFAULT (datetime('now')),
    assigned_by     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, role_id, tenant_id)
);

CREATE TABLE IF NOT EXISTS security_approvals (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT '',
    action          TEXT NOT NULL,
    resource        TEXT NOT NULL DEFAULT '',
    resource_id     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected','expired')),
    severity        TEXT NOT NULL DEFAULT 'MEDIUM',
    approver        TEXT NOT NULL DEFAULT '',
    reason          TEXT NOT NULL DEFAULT '',
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at      TEXT,
    expires_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sa_status ON security_approvals(status);
CREATE INDEX IF NOT EXISTS idx_sa_user ON security_approvals(user_id);
CREATE INDEX IF NOT EXISTS idx_sa_action ON security_approvals(action);

-- ─── RC12.5 Phase 2: ABAC Policy Tables ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_policies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT DEFAULT '',
    conditions      TEXT NOT NULL DEFAULT '{}',
    effect          TEXT NOT NULL DEFAULT 'permit'
                    CHECK (effect IN ('permit','deny')),
    priority        INTEGER NOT NULL DEFAULT 0,
    overrides_deny  INTEGER NOT NULL DEFAULT 0,
    created_by      TEXT NOT NULL DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sp_name ON security_policies(name);
CREATE INDEX IF NOT EXISTS idx_sp_effect ON security_policies(effect);
CREATE INDEX IF NOT EXISTS idx_sp_active ON security_policies(is_active);

CREATE TABLE IF NOT EXISTS policy_versions (
    id              TEXT PRIMARY KEY,
    policy_id       TEXT NOT NULL REFERENCES security_policies(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL,
    snapshot        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pv_policy ON policy_versions(policy_id);
CREATE INDEX IF NOT EXISTS idx_pv_version ON policy_versions(version);

-- ─── RC12.6: Digital Twin Tables ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS digital_twin_entities (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','inactive','maintenance','decommissioned','planned','under_review')),
    parent_id       TEXT REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    description     TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT '',
    updated_by      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_dte_type ON digital_twin_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_dte_status ON digital_twin_entities(status);
CREATE INDEX IF NOT EXISTS idx_dte_parent ON digital_twin_entities(parent_id);

CREATE TABLE IF NOT EXISTS digital_twin_organizations (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    industry        TEXT DEFAULT '',
    sector_id       TEXT DEFAULT '',
    headquarters    TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    employee_count  INTEGER DEFAULT 0,
    annual_revenue  TEXT DEFAULT '',
    founded_year    INTEGER DEFAULT 0,
    certifications  TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digital_twin_plants (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    plant_type      TEXT DEFAULT '',
    address         TEXT DEFAULT '',
    city            TEXT DEFAULT '',
    country         TEXT DEFAULT '',
    timezone        TEXT DEFAULT '',
    area_sqft       REAL DEFAULT 0.0,
    employee_count  INTEGER DEFAULT 0,
    operating_hours TEXT DEFAULT '',
    criticality_level TEXT DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS digital_twin_departments (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    department_type TEXT DEFAULT '',
    manager_id      TEXT DEFAULT '',
    budget          REAL DEFAULT 0.0,
    cost_center     TEXT DEFAULT '',
    headcount       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS digital_twin_employees (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    employee_id     TEXT DEFAULT '',
    job_title       TEXT DEFAULT '',
    role            TEXT DEFAULT '',
    email           TEXT DEFAULT '',
    phone           TEXT DEFAULT '',
    hire_date       TEXT DEFAULT '',
    department_id   TEXT DEFAULT '',
    plant_id        TEXT DEFAULT '',
    certifications  TEXT DEFAULT '[]',
    skills          TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digital_twin_assets (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    asset_type      TEXT DEFAULT '',
    serial_number   TEXT DEFAULT '',
    model           TEXT DEFAULT '',
    manufacturer    TEXT DEFAULT '',
    installation_date TEXT DEFAULT '',
    warranty_expiry TEXT DEFAULT '',
    location_id     TEXT DEFAULT '',
    department_id   TEXT DEFAULT '',
    criticality     TEXT DEFAULT 'medium',
    condition       TEXT DEFAULT 'good',
    last_maintenance TEXT DEFAULT '',
    next_maintenance TEXT DEFAULT '',
    operating_hours REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS digital_twin_technologies (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    tech_type       TEXT DEFAULT '',
    version         TEXT DEFAULT '',
    vendor          TEXT DEFAULT '',
    license_type    TEXT DEFAULT '',
    license_expiry  TEXT DEFAULT '',
    integration_points TEXT DEFAULT '[]',
    api_endpoints   TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digital_twin_documents (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    doc_type        TEXT DEFAULT '',
    file_path       TEXT DEFAULT '',
    file_size       INTEGER DEFAULT 0,
    mime_type       TEXT DEFAULT '',
    version         TEXT DEFAULT '1.0',
    effective_date  TEXT DEFAULT '',
    expiry_date     TEXT DEFAULT '',
    review_date     TEXT DEFAULT '',
    approval_status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS digital_twin_sops (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    sop_number      TEXT DEFAULT '',
    revision        TEXT DEFAULT '1.0',
    scope           TEXT DEFAULT '',
    procedure_steps TEXT DEFAULT '[]',
    safety_requirements TEXT DEFAULT '[]',
    ppe_required    TEXT DEFAULT '[]',
    frequency       TEXT DEFAULT '',
    responsible_role TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS digital_twin_compliance (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    standard        TEXT DEFAULT '',
    requirement     TEXT DEFAULT '',
    status          TEXT DEFAULT 'compliant',
    last_audit_date TEXT DEFAULT '',
    next_audit_date TEXT DEFAULT '',
    audit_frequency TEXT DEFAULT '',
    findings        TEXT DEFAULT '[]',
    corrective_actions TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digital_twin_support_records (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    ticket_number   TEXT DEFAULT '',
    priority        TEXT DEFAULT 'medium',
    category        TEXT DEFAULT '',
    reported_by     TEXT DEFAULT '',
    assigned_to     TEXT DEFAULT '',
    resolution      TEXT DEFAULT '',
    root_cause      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS digital_twin_maintenance (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    work_order_number TEXT DEFAULT '',
    maintenance_type TEXT DEFAULT '',
    asset_id        TEXT DEFAULT '',
    scheduled_date  TEXT DEFAULT '',
    completed_date  TEXT DEFAULT '',
    technician      TEXT DEFAULT '',
    duration_hours  REAL DEFAULT 0.0,
    cost            REAL DEFAULT 0.0,
    parts_used      TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS digital_twin_projects (
    entity_id       TEXT PRIMARY KEY REFERENCES digital_twin_entities(id) ON DELETE CASCADE,
    project_type    TEXT DEFAULT '',
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    budget          REAL DEFAULT 0.0,
    spent           REAL DEFAULT 0.0,
    progress        REAL DEFAULT 0.0,
    methodology     TEXT DEFAULT '',
    project_manager_id TEXT DEFAULT ''
);

-- ─── RC12.7: Connector Tables ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS connectors (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    connector_type  TEXT NOT NULL
                    CHECK (connector_type IN ('industrial','software','cloud','database','custom')),
    protocol        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'disconnected'
                    CHECK (status IN ('disconnected','connecting','connected','error','reconnecting')),
    config          TEXT NOT NULL DEFAULT '{}',
    tags            TEXT DEFAULT '[]',
    description     TEXT DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conn_type ON connectors(connector_type);
CREATE INDEX IF NOT EXISTS idx_conn_status ON connectors(status);
CREATE INDEX IF NOT EXISTS idx_conn_protocol ON connectors(protocol);

CREATE TABLE IF NOT EXISTS connector_data_points (
    id              TEXT PRIMARY KEY,
    connector_id    TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    data_type       TEXT DEFAULT 'string',
    description     TEXT DEFAULT '',
    unit            TEXT DEFAULT '',
    min_value       REAL,
    max_value       REAL,
    is_writable     INTEGER NOT NULL DEFAULT 0,
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cdp_connector ON connector_data_points(connector_id);

CREATE TABLE IF NOT EXISTS connector_logs (
    id              TEXT PRIMARY KEY,
    connector_id    TEXT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    operation       TEXT NOT NULL
                    CHECK (operation IN ('connect','disconnect','read','write','subscribe','unsubscribe','health_check')),
    status          TEXT NOT NULL DEFAULT 'success'
                    CHECK (status IN ('success','error','timeout')),
    path            TEXT DEFAULT '',
    duration_ms     INTEGER DEFAULT 0,
    error_message   TEXT DEFAULT '',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cl_connector ON connector_logs(connector_id);
CREATE INDEX IF NOT EXISTS idx_cl_operation ON connector_logs(operation);
CREATE INDEX IF NOT EXISTS idx_cl_status ON connector_logs(status);

-- ─── RC12.8: Project Management OS Tables ───────────────────────────────────

CREATE TABLE IF NOT EXISTS projectos_organizations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    industry        TEXT DEFAULT '',
    sector_id       TEXT DEFAULT '',
    headquarters    TEXT DEFAULT '',
    website         TEXT DEFAULT '',
    employee_count  INTEGER DEFAULT 0,
    founded_year    INTEGER DEFAULT 0,
    certifications  TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS projectos_programs (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES projectos_organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning','active','on_hold','completed')),
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    budget          REAL DEFAULT 0.0,
    spent           REAL DEFAULT 0.0,
    manager_id      TEXT DEFAULT '',
    objectives      TEXT DEFAULT '[]',
    kpis            TEXT DEFAULT '{}',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pp_org ON projectos_programs(organization_id);

CREATE TABLE IF NOT EXISTS projectos_projects (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES projectos_organizations(id) ON DELETE CASCADE,
    program_id      TEXT REFERENCES projectos_programs(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning','active','on_hold','completed','cancelled')),
    priority        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('critical','high','medium','low')),
    methodology     TEXT DEFAULT '',
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    budget          REAL DEFAULT 0.0,
    spent           REAL DEFAULT 0.0,
    progress        REAL DEFAULT 0.0,
    manager_id      TEXT DEFAULT '',
    owner_id        TEXT DEFAULT '',
    team_ids        TEXT DEFAULT '[]',
    agent_ids       TEXT DEFAULT '[]',
    connector_ids   TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pj_org ON projectos_projects(organization_id);
CREATE INDEX IF NOT EXISTS idx_pj_program ON projectos_projects(program_id);
CREATE INDEX IF NOT EXISTS idx_pj_status ON projectos_projects(status);

CREATE TABLE IF NOT EXISTS projectos_sprints (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    number          INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning','active','review','retrospective','completed')),
    goal            TEXT DEFAULT '{}',
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    capacity_hours  REAL DEFAULT 0.0,
    committed_points INTEGER DEFAULT 0,
    completed_points INTEGER DEFAULT 0,
    velocity        REAL DEFAULT 0.0,
    retrospective_notes TEXT DEFAULT '',
    item_ids        TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sp_project ON projectos_sprints(project_id);

CREATE TABLE IF NOT EXISTS projectos_backlog_items (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    sprint_id       TEXT REFERENCES projectos_sprints(id) ON DELETE SET NULL,
    parent_id       TEXT REFERENCES projectos_backlog_items(id) ON DELETE SET NULL,
    type            TEXT NOT NULL DEFAULT 'task'
                    CHECK (type IN ('epic','feature','story','task','bug','spike')),
    status          TEXT NOT NULL DEFAULT 'backlog'
                    CHECK (status IN ('backlog','ready','in_progress','in_review','testing','done')),
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    acceptance_criteria TEXT DEFAULT '[]',
    story_points    INTEGER DEFAULT 0,
    priority        INTEGER DEFAULT 0,
    assignee_id     TEXT DEFAULT '',
    agent_id        TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    dependencies    TEXT DEFAULT '[]',
    blocked_by      TEXT DEFAULT '[]',
    comments        TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_bi_project ON projectos_backlog_items(project_id);
CREATE INDEX IF NOT EXISTS idx_bi_sprint ON projectos_backlog_items(sprint_id);
CREATE INDEX IF NOT EXISTS idx_bi_status ON projectos_backlog_items(status);

CREATE TABLE IF NOT EXISTS projectos_missions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    parent_mission_id TEXT REFERENCES projectos_missions(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','planning','ready','in_progress','on_hold','completed','failed','cancelled')),
    objective       TEXT DEFAULT '',
    deliverables    TEXT DEFAULT '[]',
    success_criteria TEXT DEFAULT '[]',
    assigned_agent_ids TEXT DEFAULT '[]',
    assigned_team_id TEXT DEFAULT '',
    task_ids        TEXT DEFAULT '[]',
    start_date      TEXT DEFAULT '',
    end_date        TEXT DEFAULT '',
    estimated_hours REAL DEFAULT 0.0,
    actual_hours    REAL DEFAULT 0.0,
    budget          REAL DEFAULT 0.0,
    spent           REAL DEFAULT 0.0,
    risk_level      TEXT DEFAULT 'low',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ms_project ON projectos_missions(project_id);
CREATE INDEX IF NOT EXISTS idx_ms_status ON projectos_missions(status);

CREATE TABLE IF NOT EXISTS projectos_tasks (
    id              TEXT PRIMARY KEY,
    mission_id      TEXT NOT NULL REFERENCES projectos_missions(id) ON DELETE CASCADE,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    parent_task_id  TEXT REFERENCES projectos_tasks(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo','in_progress','blocked','in_review','completed','cancelled')),
    priority        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('critical','high','medium','low')),
    task_type       TEXT NOT NULL DEFAULT 'development'
                    CHECK (task_type IN ('development','testing','documentation','deployment','review','research','maintenance')),
    assignee_id     TEXT DEFAULT '',
    agent_id        TEXT DEFAULT '',
    estimated_hours REAL DEFAULT 0.0,
    actual_hours    REAL DEFAULT 0.0,
    story_points    INTEGER DEFAULT 0,
    dependencies    TEXT DEFAULT '[]',
    blocked_by      TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    comments        TEXT DEFAULT '[]',
    attachments     TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tk_mission ON projectos_tasks(mission_id);
CREATE INDEX IF NOT EXISTS idx_tk_project ON projectos_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tk_status ON projectos_tasks(status);

CREATE TABLE IF NOT EXISTS projectos_resources (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    resource_type   TEXT NOT NULL DEFAULT 'human'
                    CHECK (resource_type IN ('human','ai_agent','ai_model','connector','tool','infrastructure')),
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'available',
    hourly_cost     REAL DEFAULT 0.0,
    skills          TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rs_type ON projectos_resources(resource_type);

CREATE TABLE IF NOT EXISTS projectos_knowledge_documents (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    knowledge_type  TEXT NOT NULL DEFAULT 'documentation'
                    CHECK (knowledge_type IN ('documentation','requirement','specification','architecture','adr','lesson_learned','support_history','meeting_notes','sop','changelog','runbook')),
    title           TEXT NOT NULL,
    content         TEXT DEFAULT '',
    summary         TEXT DEFAULT '',
    author_id       TEXT DEFAULT '',
    version         TEXT NOT NULL DEFAULT '1.0',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','reviewed','approved','archived')),
    tags            TEXT DEFAULT '[]',
    related_doc_ids TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kd_project ON projectos_knowledge_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_kd_type ON projectos_knowledge_documents(knowledge_type);

CREATE TABLE IF NOT EXISTS projectos_diagrams (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    diagram_type    TEXT NOT NULL DEFAULT 'architecture'
                    CHECK (diagram_type IN ('process','architecture','component','sequence','er','network','infrastructure','security','flowchart','mind_map')),
    version         TEXT NOT NULL DEFAULT '1.0',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','active','archived')),
    nodes           TEXT DEFAULT '[]',
    edges           TEXT DEFAULT '[]',
    style           TEXT DEFAULT '{}',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_dg_project ON projectos_diagrams(project_id);
CREATE INDEX IF NOT EXISTS idx_dg_type ON projectos_diagrams(diagram_type);

CREATE TABLE IF NOT EXISTS projectos_process_models (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    process_type    TEXT NOT NULL DEFAULT 'flowchart'
                    CHECK (process_type IN ('bpmn','flowchart','process_map','sop_flow','approval_flow','incident_flow')),
    version         TEXT NOT NULL DEFAULT '1.0',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','active','archived')),
    nodes           TEXT DEFAULT '[]',
    edges           TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pm_project ON projectos_process_models(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_type ON projectos_process_models(process_type);

-- ─── RC12.8.1: Portfolio, Milestone, Risk, KPI, Dependency Tables ───────────

CREATE TABLE IF NOT EXISTS projectos_portfolios (
    id              TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES projectos_organizations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'planning'
                    CHECK (status IN ('planning','active','on_hold','completed')),
    strategic_goals TEXT DEFAULT '[]',
    budget          REAL DEFAULT 0.0,
    spent           REAL DEFAULT 0.0,
    program_ids     TEXT DEFAULT '[]',
    project_ids     TEXT DEFAULT '[]',
    risk_ids        TEXT DEFAULT '[]',
    kpi_ids         TEXT DEFAULT '[]',
    owner_id        TEXT DEFAULT '',
    sponsor_id      TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pf_org ON projectos_portfolios(organization_id);
CREATE INDEX IF NOT EXISTS idx_pf_status ON projectos_portfolios(status);

CREATE TABLE IF NOT EXISTS projectos_milestones (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    due_date        TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','in_progress','completed','overdue','at_risk')),
    progress        REAL DEFAULT 0.0,
    deliverables    TEXT DEFAULT '[]',
    dependency_ids  TEXT DEFAULT '[]',
    blocked_by      TEXT DEFAULT '[]',
    task_ids        TEXT DEFAULT '[]',
    owner_id        TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ml_project ON projectos_milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_ml_status ON projectos_milestones(status);
CREATE INDEX IF NOT EXISTS idx_ml_due ON projectos_milestones(due_date);

CREATE TABLE IF NOT EXISTS projectos_risks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    portfolio_id    TEXT REFERENCES projectos_portfolios(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    severity        TEXT NOT NULL DEFAULT 'medium'
                    CHECK (severity IN ('critical','high','medium','low')),
    probability     TEXT NOT NULL DEFAULT 'medium'
                    CHECK (probability IN ('very_high','high','medium','low','very_low')),
    impact          TEXT DEFAULT '',
    risk_score      REAL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'identified'
                    CHECK (status IN ('identified','assessed','mitigating','monitoring','closed')),
    mitigation_strategy TEXT DEFAULT '',
    contingency_plan TEXT DEFAULT '',
    owner_id        TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    related_mission_ids TEXT DEFAULT '[]',
    related_task_ids TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    identified_at   TEXT DEFAULT '',
    closed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_rk_project ON projectos_risks(project_id);
CREATE INDEX IF NOT EXISTS idx_rk_severity ON projectos_risks(severity);
CREATE INDEX IF NOT EXISTS idx_rk_status ON projectos_risks(status);

CREATE TABLE IF NOT EXISTS projectos_kpis (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    portfolio_id    TEXT REFERENCES projectos_portfolios(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    metric          TEXT DEFAULT '',
    unit            TEXT DEFAULT '',
    target_value    REAL DEFAULT 0.0,
    actual_value    REAL DEFAULT 0.0,
    trend           TEXT NOT NULL DEFAULT 'stable'
                    CHECK (trend IN ('up','down','stable')),
    status          TEXT NOT NULL DEFAULT 'on_track'
                    CHECK (status IN ('on_track','at_risk','off_track')),
    threshold_warning REAL DEFAULT 0.0,
    threshold_critical REAL DEFAULT 0.0,
    frequency       TEXT NOT NULL DEFAULT 'sprint'
                    CHECK (frequency IN ('daily','weekly','sprint','monthly','quarterly')),
    owner_id        TEXT DEFAULT '',
    data_points     TEXT DEFAULT '[]',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kp_project ON projectos_kpis(project_id);
CREATE INDEX IF NOT EXISTS idx_kp_status ON projectos_kpis(status);

CREATE TABLE IF NOT EXISTS projectos_dependencies (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projectos_projects(id) ON DELETE CASCADE,
    name            TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    source_id       TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'task',
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL DEFAULT 'task',
    dependency_type TEXT NOT NULL DEFAULT 'finish_to_start'
                    CHECK (dependency_type IN ('finish_to_start','start_to_start','finish_to_finish','start_to_finish')),
    is_blocking     INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','resolved','cancelled')),
    lag_days        INTEGER DEFAULT 0,
    lead_days       INTEGER DEFAULT 0,
    owner_id        TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_dp_project ON projectos_dependencies(project_id);
CREATE INDEX IF NOT EXISTS idx_dp_source ON projectos_dependencies(source_id);
CREATE INDEX IF NOT EXISTS idx_dp_target ON projectos_dependencies(target_id);
CREATE INDEX IF NOT EXISTS idx_dp_status ON projectos_dependencies(status);

-- RC12.8.2: Reports
CREATE TABLE IF NOT EXISTS projectos_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    report_type TEXT DEFAULT 'daily',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'generating', 'generated', 'delivered', 'failed')),
    sections TEXT DEFAULT '[]',
    author_id TEXT DEFAULT '',
    format TEXT DEFAULT 'html',
    date_from TEXT DEFAULT '',
    date_to TEXT DEFAULT '',
    generated_at TEXT DEFAULT '',
    delivered_at TEXT DEFAULT '',
    delivered_to TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projectos_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rpt_project ON projectos_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_rpt_type ON projectos_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_rpt_status ON projectos_reports(status);

-- RC12.8.2: Notifications
CREATE TABLE IF NOT EXISTS projectos_notifications (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    event TEXT DEFAULT 'custom',
    priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'delivered', 'read', 'failed')),
    subject TEXT DEFAULT '',
    body TEXT DEFAULT '',
    channels TEXT DEFAULT '[]',
    recipient_ids TEXT DEFAULT '[]',
    sender_id TEXT DEFAULT '',
    related_entity_type TEXT DEFAULT '',
    related_entity_id TEXT DEFAULT '',
    template_id TEXT DEFAULT '',
    delivered_at TEXT DEFAULT '',
    read_at TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projectos_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notif_project ON projectos_notifications(project_id);
CREATE INDEX IF NOT EXISTS idx_notif_event ON projectos_notifications(event);
CREATE INDEX IF NOT EXISTS idx_notif_status ON projectos_notifications(status);

-- RC12.8.2: Notification Templates
CREATE TABLE IF NOT EXISTS projectos_notification_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    event TEXT DEFAULT 'custom',
    subject_template TEXT DEFAULT '',
    body_template TEXT DEFAULT '',
    channels TEXT DEFAULT '[]',
    enabled INTEGER DEFAULT 1,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

-- RC12.8.2: Project Documents
CREATE TABLE IF NOT EXISTS projectos_documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    knowledge_base_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    format TEXT DEFAULT 'txt',
    status TEXT DEFAULT 'uploaded',
    file_path TEXT DEFAULT '',
    metadata_doc TEXT DEFAULT '{}',
    extractions TEXT DEFAULT '[]',
    summary TEXT DEFAULT '',
    content_preview TEXT DEFAULT '',
    version INTEGER DEFAULT 1,
    uploaded_by TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    related_task_ids TEXT DEFAULT '[]',
    related_requirement_ids TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projectos_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_doc_project ON projectos_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_doc_format ON projectos_documents(format);
CREATE INDEX IF NOT EXISTS idx_doc_status ON projectos_documents(status);

-- RC12.8.2: Requirements
CREATE TABLE IF NOT EXISTS projectos_requirements (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    requirement_type TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    source_page INTEGER DEFAULT 0,
    source_section TEXT DEFAULT '',
    status TEXT DEFAULT 'identified',
    converted_task_id TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES projectos_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projectos_projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_req_project ON projectos_requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_req_document ON projectos_requirements(document_id);
CREATE INDEX IF NOT EXISTS idx_req_status ON projectos_requirements(status);

-- RC12.8.2: Memory Entries
CREATE TABLE IF NOT EXISTS projectos_memory_entries (
    id TEXT PRIMARY KEY,
    tier TEXT DEFAULT 'global' CHECK (tier IN ('global', 'organization', 'project', 'team', 'user')),
    memory_type TEXT DEFAULT 'knowledge' CHECK (memory_type IN ('knowledge', 'decision', 'experience', 'pattern', 'error', 'lesson', 'preference', 'context')),
    title TEXT NOT NULL,
    content TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    entity_type TEXT DEFAULT '',
    entity_id TEXT DEFAULT '',
    author_id TEXT DEFAULT '',
    access_level TEXT DEFAULT 'public' CHECK (access_level IN ('public', 'organization', 'project', 'private')),
    retention_policy TEXT DEFAULT 'permanent',
    tags TEXT DEFAULT '[]',
    version INTEGER DEFAULT 1,
    parent_id TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_mem_tier ON projectos_memory_entries(tier);
CREATE INDEX IF NOT EXISTS idx_mem_entity ON projectos_memory_entries(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_mem_type ON projectos_memory_entries(memory_type);

-- RC12.8.2: Memory Stores
CREATE TABLE IF NOT EXISTS projectos_memory_stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT DEFAULT 'global' CHECK (tier IN ('global', 'organization', 'project', 'team', 'user')),
    entity_type TEXT DEFAULT '',
    entity_id TEXT DEFAULT '',
    entry_count INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,
    last_compaction TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_memstore_tier ON projectos_memory_stores(tier);
CREATE INDEX IF NOT EXISTS idx_memstore_entity ON projectos_memory_stores(entity_type, entity_id);
"""


class Database:
    """Async SQLite database manager for EMO AI."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.getenv("EMO_DB_PATH", "emo_ai.db")
        self._initialized = False
        self._backend = create_backend()

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[Connection]:
        conn = await self._backend.connect()
        try:
            yield conn
        finally:
            await conn.close()

    _JSON_FIELDS_SKILL = frozenset({
        "required_tools", "required_models", "required_permissions",
        "input_schema", "output_schema", "metadata", "execution_history",
        "config",
    })

    @staticmethod
    def _decode_row(row, json_fields=None):
        """Safely decode a sqlite Row into a dict with JSON fields parsed.

        - Converts sqlite Row to dict
        - Parses JSON only for specified fields
        - Never raises: NULL, plain string, or corrupted JSON → safe fallback
        """
        if row is None:
            return None
        d = dict(row)
        if not json_fields:
            return d
        for field in json_fields:
            val = d.get(field)
            if val is None or val == "":
                d[field] = [] if "tools" in field or "permissions" in field or "history" in field else {}
                continue
            if isinstance(val, (list, dict)):
                continue
            if not isinstance(val, str):
                d[field] = val
                continue
            try:
                d[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError, ValueError):
                d[field] = [] if "tools" in field or "permissions" in field or "history" in field else {}
        return d

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        if self._initialized:
            return
        async with self._connect() as db:
            await db.executescript(INIT_SQL)
            # Migration: add is_archived column to conversations if it doesn't exist
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
                await db.commit()
            except Exception:
                pass
            # Migration: add project_id and session_id to conversations
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT REFERENCES projects(id)")
                await db.commit()
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT REFERENCES project_sessions(id)")
                await db.commit()
            except Exception:
                pass
            # Migration: add project_id and session_id to tasks
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT REFERENCES projects(id)")
                await db.commit()
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN session_id TEXT REFERENCES project_sessions(id)")
                await db.commit()
            except Exception:
                pass
            # Migration: v1.1 Chat Identity - mission_id and mode on tasks
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN mission_id TEXT")
                await db.commit()
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN mode TEXT DEFAULT 'manual'")
                await db.commit()
            except Exception:
                pass
            # Migration RC12.4.1: skill_execution_history table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS skill_execution_history (
                        id              TEXT PRIMARY KEY,
                        skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                        mission_id      TEXT NOT NULL DEFAULT '',
                        agent_id        TEXT NOT NULL DEFAULT '',
                        success         INTEGER NOT NULL DEFAULT 1,
                        duration        REAL NOT NULL DEFAULT 0.0,
                        cost            REAL NOT NULL DEFAULT 0.0,
                        error           TEXT NOT NULL DEFAULT '',
                        metadata        TEXT NOT NULL DEFAULT '{}',
                        created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.execute("CREATE INDEX IF NOT EXISTS idx_seh_skill ON skill_execution_history(skill_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_seh_mission ON skill_execution_history(mission_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_seh_created ON skill_execution_history(created_at)")
                await db.commit()
            except Exception:
                pass
            # Migration RC12.4.1: skill_versions table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS skill_versions (
                        id              TEXT PRIMARY KEY,
                        skill_id        TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                        version         TEXT NOT NULL,
                        config          TEXT NOT NULL DEFAULT '{}',
                        created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                        created_by      TEXT NOT NULL DEFAULT '',
                        approved_by     TEXT NOT NULL DEFAULT ''
                    )
                """)
                await db.execute("CREATE INDEX IF NOT EXISTS idx_sv_skill ON skill_versions(skill_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_sv_version ON skill_versions(skill_id, version)")
                await db.commit()
            except Exception:
                pass
            # Migration RC12.5.1: identity_roles table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS identity_roles (
                        id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                        level INTEGER NOT NULL DEFAULT 0, description TEXT NOT NULL DEFAULT '',
                        can_approve INTEGER NOT NULL DEFAULT 0, can_deploy INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                """)
                await db.commit()
            except Exception:
                pass
            # Migration RC12.5.1: identity_permissions table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS identity_permissions (
                        id TEXT PRIMARY KEY, resource TEXT NOT NULL, action TEXT NOT NULL,
                        scope TEXT NOT NULL DEFAULT 'own', require_approval INTEGER NOT NULL DEFAULT 0,
                        require_mfa INTEGER NOT NULL DEFAULT 0, UNIQUE(resource, action, scope)
                    )
                """)
                await db.commit()
            except Exception:
                pass
            # Migration RC12.5.1: identity_role_permissions table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS identity_role_permissions (
                        role_id TEXT NOT NULL REFERENCES identity_roles(id) ON DELETE CASCADE,
                        permission_id TEXT NOT NULL REFERENCES identity_permissions(id) ON DELETE CASCADE,
                        PRIMARY KEY (role_id, permission_id)
                    )
                """)
                await db.commit()
            except Exception:
                pass
            # Migration RC12.5.1: identity_user_roles table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS identity_user_roles (
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        role_id TEXT NOT NULL REFERENCES identity_roles(id) ON DELETE CASCADE,
                        tenant_id TEXT NOT NULL DEFAULT '', org_id TEXT NOT NULL DEFAULT '',
                        assigned_at TEXT NOT NULL DEFAULT (datetime('now')),
                        assigned_by TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (user_id, role_id, tenant_id)
                    )
                """)
                await db.commit()
            except Exception:
                pass
            # Migration RC12.5.1: security_approvals table
            try:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS security_approvals (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT '',
                        action TEXT NOT NULL, resource TEXT NOT NULL DEFAULT '',
                        resource_id TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','approved','rejected','expired')),
                        severity TEXT NOT NULL DEFAULT 'MEDIUM',
                        approver TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        decided_at TEXT, expires_at TEXT
                    )
                """)
                await db.execute("CREATE INDEX IF NOT EXISTS idx_sa_status ON security_approvals(status)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_sa_user ON security_approvals(user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_sa_action ON security_approvals(action)")
                await db.commit()
            except Exception:
                pass
            # Migration: seed identity_roles from unified RBAC
            try:
                from core.security.rbac import ROLE_DEFINITIONS
                for role_def in ROLE_DEFINITIONS.values():
                    await db.execute(
                        """INSERT OR IGNORE INTO identity_roles
                        (id, name, level, description, can_approve, can_deploy)
                        VALUES (?, ?, ?, ?, ?, ?)""",
                        (role_def.role.value, role_def.role.value, role_def.level,
                         role_def.description, 1 if role_def.can_approve else 0,
                         1 if role_def.can_deploy else 0),
                    )
                await db.commit()
            except Exception:
                pass
            await db.commit()
        self._initialized = True

    # ── Security helpers ──────────────────────────────────────────────

    @staticmethod
    def _whitelist_columns(
        allowed: frozenset,
        provided: Dict[str, object],
        table_label: str = "table",
    ) -> str:
        """Build a safe ``SET col = ?, col2 = ?`` string from *provided*
        after validating every key against *allowed*.

        Raises *InvalidColumnError* (a ``SecurityError``) if any key in
        *provided* is not in *allowed*.
        """
        bad = [k for k in provided if k not in allowed]
        if bad:
            raise InvalidColumnError(
                f"Unwhitelisted column(s) {bad} for {table_label}. "
                f"Allowed: {sorted(allowed)}."
            )
        return ", ".join(f"{k} = ?" for k in provided.keys())

    # --- Tasks ---

    async def create_task(
        self,
        task_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO tasks (id, message, conversation_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (task_id, message, conversation_id, now, now),
            )
            await db.commit()
        return {
            "id": task_id,
            "message": message,
            "status": "pending",
            "created_at": now,
        }

    async def update_task(
        self,
        task_id: str,
        **kwargs,
    ) -> Optional[Dict]:
        now = datetime.utcnow().isoformat()
        fields = self._whitelist_columns(ALLOWED_TASK_COLUMNS, kwargs, "tasks")
        values = list(kwargs.values()) + [now, task_id]
        async with self._connect() as db:
            await db.execute(
                f"UPDATE tasks SET {fields}, updated_at = ? WHERE id = ?",
                values,
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def get_task(self, task_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def list_tasks(
        self,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> List[Dict]:
        query = "SELECT * FROM tasks"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with self._connect() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """Delete tasks older than max_age_hours."""
        async with self._connect() as db:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE created_at < datetime('now', ?)",
                (f"-{max_age_hours} hours",),
            )
            await db.commit()
            return cursor.rowcount

    # --- Agents (v1.1 Phase 3) ---

    async def create_agent(
        self,
        agent_id: str,
        name: str,
        display_name: str,
        role: str,
        description: str = "",
        icon: str = "fa-robot",
        color: str = "var(--emo-blue-light)",
        status: str = "online",
        model_binding: Optional[Dict] = None,
        tools: Optional[List[str]] = None,
        memory: Optional[Dict] = None,
        execution_policy: Optional[Dict] = None,
        system_prompt: str = "",
        is_built_in: int = 0,
    ) -> Dict:
        import json as _json
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO agents
                (id, name, display_name, role, description, icon, color, status,
                 model_binding, tools, memory, execution_policy, system_prompt, is_built_in)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id, name, display_name, role, description, icon, color, status,
                    _json.dumps(model_binding or {}),
                    _json.dumps(tools or []),
                    _json.dumps(memory or {"type": "none", "scope": "none"}),
                    _json.dumps(execution_policy or {"mode": "manual", "permissions": ["sandbox"], "timeout": 60, "max_tokens": 2048}),
                    system_prompt,
                    is_built_in,
                ),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def get_agent(self, agent_id: str) -> Optional[Dict]:
        import json as _json
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
            row = await cursor.fetchone()
        if not row:
            return None
        d = self._row_to_dict(row, cursor.description)
        # Parse JSON fields
        for field in ("model_binding", "tools", "memory", "execution_policy", "tools_used"):
            if d.get(field):
                try:
                    d[field] = _json.loads(d[field])
                except Exception:
                    d[field] = {} if field != "tools" and field != "tools_used" else []
            else:
                d[field] = {} if field != "tools" and field != "tools_used" else []
        return d

    async def list_agents(self, status: Optional[str] = None) -> List[Dict]:
        import json as _json
        async with self._connect() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM agents WHERE status = ? ORDER BY is_built_in DESC, name ASC",
                    (status,),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM agents ORDER BY is_built_in DESC, name ASC"
                )
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = self._row_to_dict(row, cursor.description)
            for field in ("model_binding", "tools", "memory", "execution_policy", "tools_used"):
                if d.get(field):
                    try:
                        d[field] = _json.loads(d[field])
                    except Exception:
                        d[field] = {} if field != "tools" and field != "tools_used" else []
                else:
                    d[field] = {} if field != "tools" and field != "tools_used" else []
            result.append(d)
        return result

    async def update_agent(self, agent_id: str, **kwargs) -> Optional[Dict]:
        import json as _json
        # Serialize any dict/list fields
        for field in ("model_binding", "tools", "memory", "execution_policy", "tools_used"):
            if field in kwargs and isinstance(kwargs[field], (dict, list)):
                kwargs[field] = _json.dumps(kwargs[field])
        fields = self._whitelist_columns(ALLOWED_AGENT_COLUMNS, kwargs, "agents")
        values = list(kwargs.values()) + [datetime.utcnow().isoformat(), agent_id]
        async with self._connect() as db:
            await db.execute(
                f"UPDATE agents SET {fields}, updated_at = ? WHERE id = ?",
                values,
            )
            await db.commit()
        return await self.get_agent(agent_id)

    async def delete_agent(self, agent_id: str) -> bool:
        async with self._connect() as db:
            # Don't allow deleting built-in agents
            cursor = await db.execute("SELECT is_built_in FROM agents WHERE id = ?", (agent_id,))
            row = await cursor.fetchone()
            if not row:
                return False
            if row[0] == 1:
                return False  # Cannot delete built-in
            await db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            await db.commit()
        return True

    async def record_agent_run(self, agent_id: str, success: bool, tools_used: Optional[List[str]] = None) -> None:
        """Update health metrics after an agent run."""
        async with self._connect() as db:
            if tools_used:
                import json as _json
                tools_str = _json.dumps(tools_used)
            else:
                tools_str = None
            if success:
                await db.execute(
                    """UPDATE agents
                    SET task_count = task_count + 1,
                        success_count = success_count + 1,
                        last_run_at = datetime('now'),
                        tools_used = COALESCE(?, tools_used)
                    WHERE id = ?""",
                    (tools_str, agent_id),
                )
            else:
                await db.execute(
                    """UPDATE agents
                    SET task_count = task_count + 1,
                        error_count = error_count + 1,
                        last_run_at = datetime('now')
                    WHERE id = ?""",
                    (agent_id,),
                )
            await db.commit()

    async def seed_default_agents(self) -> None:
        """Seed the 4 built-in agents if they don't exist."""
        import json as _json
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM agents")
            count = (await cursor.fetchone())[0]
            if count > 0:
                return  # Already seeded
            defaults = [
                {
                    "id": "planner", "name": "planner", "display_name": "Planner",
                    "role": "Task Planner & Distributor",
                    "description": "Analyzes tasks and breaks them into actionable steps. Routes work to specialized agents.",
                    "icon": "fa-sitemap", "color": "var(--emo-agent-planner)",
                    "system_prompt": "You are a task planner and distributor. Analyze the user's request and break it down into actionable steps. Be concise and structured.",
                    "tools": ["project_analyzer", "directory_lister", "file_reader", "project_monitor"],
                    "memory": {"type": "session", "scope": "conversation"},
                    "execution_policy": {"mode": "manual", "permissions": ["sandbox"], "timeout": 60, "max_tokens": 2048},
                },
                {
                    "id": "coder", "name": "coder", "display_name": "Coder",
                    "role": "Software Engineer",
                    "description": "Writes clean, professional, well-documented code. Follows best practices and explains decisions.",
                    "icon": "fa-code", "color": "var(--emo-agent-coder)",
                    "system_prompt": "You are an expert software engineer. Write clean, professional, well-documented code. Follow best practices and explain your decisions.",
                    "tools": ["file_reader", "directory_lister", "codebase_refactor", "auto_debugger", "ai_code_reviewer", "dependency_manager", "project_scaffold", "github_read_file", "github_write_file", "github_create_branch"],
                    "memory": {"type": "project", "scope": "project"},
                    "execution_policy": {"mode": "manual", "permissions": ["sandbox", "filesystem", "network"], "timeout": 180, "max_tokens": 4096},
                },
                {
                    "id": "writer", "name": "writer", "display_name": "Writer",
                    "role": "Content Writer",
                    "description": "Writes clear, engaging, well-structured content. Adapts tone to context.",
                    "icon": "fa-feather-pointed", "color": "var(--emo-agent-writer)",
                    "system_prompt": "You are a professional writer and content creator. Write clear, engaging, and well-structured content. Adapt your tone to the context.",
                    "tools": ["file_reader", "directory_lister"],
                    "memory": {"type": "session", "scope": "conversation"},
                    "execution_policy": {"mode": "manual", "permissions": ["sandbox"], "timeout": 60, "max_tokens": 2048},
                },
                {
                    "id": "researcher", "name": "researcher", "display_name": "Researcher",
                    "role": "Research Analyst",
                    "description": "Provides thorough, fact-based analysis with citations where possible.",
                    "icon": "fa-search", "color": "var(--emo-agent-researcher)",
                    "system_prompt": "You are a research analyst. Provide thorough, fact-based analysis with citations where possible. Be objective and comprehensive.",
                    "tools": ["project_analyzer", "file_reader", "github_read_file", "directory_lister"],
                    "memory": {"type": "project", "scope": "project"},
                    "execution_policy": {"mode": "manual", "permissions": ["sandbox", "network"], "timeout": 120, "max_tokens": 4096},
                },
            ]
            for a in defaults:
                await db.execute(
                    """INSERT INTO agents
                    (id, name, display_name, role, description, icon, color, status,
                     model_binding, tools, memory, execution_policy, system_prompt, is_built_in)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        a["id"], a["name"], a["display_name"], a["role"], a["description"],
                        a["icon"], a["color"], "online",
                        _json.dumps({"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct", "parameters": {"temperature": 0.7, "context": 4096, "max_output": 2048}}),
                        _json.dumps(a["tools"]),
                        _json.dumps(a["memory"]),
                        _json.dumps(a["execution_policy"]),
                        a["system_prompt"],
                        1,  # is_built_in
                    ),
                )
            await db.commit()

    # --- Enterprise seeding (v1.1 Phase 5) ---

    async def seed_default_enterprise(self) -> None:
        """Seed a default Organization + Super Admin user on first boot."""
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM enterprise_orgs")
            count = (await cursor.fetchone())[0]
            if count > 0:
                return  # Already seeded

            # 1. Default Org
            await db.execute(
                """INSERT INTO enterprise_orgs
                (id, name, sector, region, compliance_profile, policy_id, deployment_profile, status, config, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "org_default", "Default Organization", "enterprise_it", "global",
                    "iso27001", "default", "development", "active",
                    '{"language": "ar", "theme": "dark", "timezone": "Asia/Riyadh"}',
                    '{}',
                ),
            )

            # 2. Super Admin user
            await db.execute(
                """INSERT INTO enterprise_users
                (id, email, organization_id, display_name, role, status, mfa_enabled, department, scopes, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "user_super_admin", "admin@emo.ai", "org_default",
                    "System Administrator", "super_admin", "active", 1,
                    "Operations", "admin:full", '{}',
                ),
            )

            # 3. Default Policy (matches `core.enterprise.policy.default`)
            await db.execute(
                """INSERT INTO enterprise_policies
                (id, name, organization_id, description, allowed_tools, blocked_tools, approval_required_for,
                 max_timeout_s, max_memory_mb, max_calls_per_mission, max_concurrent_missions,
                 require_mfa_for, deny_after_hours, allowed_hours, active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "default", "Default Permissive Policy", "org_default",
                    "Initial policy. Permissive: allows all tools, no approval required.",
                    "", "", "",
                    60, 256, 100, 5,
                    "", 0, '{}', 1, '{}',
                ),
            )

            # 4. Industrial Policy
            await db.execute(
                """INSERT INTO enterprise_policies
                (id, name, organization_id, description, allowed_tools, blocked_tools, approval_required_for,
                 max_timeout_s, max_memory_mb, max_calls_per_mission, max_concurrent_missions,
                 require_mfa_for, deny_after_hours, allowed_hours, active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "industrial", "Industrial Zero-Trust Policy", "org_default",
                    "Strict industrial policy: zero-trust, MFA for sensitive, after-hours deny, full audit.",
                    "", "",
                    "file_delete,project_structure_edit,permission_grant,deploy,config_change",
                    45, 192, 80, 3,
                    "file_delete,deploy,permission_grant", 1, '{}', 1, '{"zero_trust": true}',
                ),
            )

            # 5. Production Policy
            await db.execute(
                """INSERT INTO enterprise_policies
                (id, name, organization_id, description, allowed_tools, blocked_tools, approval_required_for,
                 max_timeout_s, max_memory_mb, max_calls_per_mission, max_concurrent_missions,
                 require_mfa_for, deny_after_hours, allowed_hours, active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "production", "Production Approval Policy", "org_default",
                    "Production policy: approval required for sensitive operations.",
                    "", "",
                    "file_delete,project_structure_edit,deploy",
                    60, 256, 100, 5,
                    "deploy", 0, '{}', 1, '{}',
                ),
            )

            # 6. Initial audit entry
            await db.execute(
                """INSERT INTO enterprise_audit
                (id, action, who, user_email, user_role, org_id, agent_id, tool, subject, result, approval_id, severity, deployment, context, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    "audit_seed_001", "SYSTEM_SEED", "system", "admin@emo.ai", "super_admin",
                    "org_default", "", "", "enterprise.bootstrap", "ok", "",
                    "INFO", "development", '{"event": "default_org_created", "users": 1, "policies": 3}',
                ),
            )

            await db.commit()

    # --- Missions (v1.1 Phase 4) ---

    MISSION_COLUMNS = frozenset({
        "goal", "intent", "plan", "agents", "tools", "status", "current_step",
        "progress", "errors", "validation", "result",
        "project_id", "conversation_id", "execution_log",
        "started_at", "completed_at",
    })

    async def create_mission(
        self,
        mission_id: str,
        goal: str,
        intent: str = "{}",
        plan: str = "[]",
        agents: str = "[]",
        tools: str = "[]",
        project_id: str = "",
        conversation_id: str = "",
        execution_log: str = "[]",
    ) -> Dict:
        import json as _json
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO missions
                (id, goal, intent, plan, agents, tools, status, current_step,
                 progress, errors, validation, result, project_id, conversation_id, execution_log)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, '{}', '[]', '[]', '{}', ?, ?, ?)""",
                (mission_id, goal, intent, plan, agents, tools,
                 project_id, conversation_id, execution_log),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def get_mission(self, mission_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else None

    async def list_missions(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        project_id: Optional[str] = None,
    ) -> List[Dict]:
        async with self._connect() as db:
            q = "SELECT * FROM missions"
            params: List = []
            conds: List[str] = []
            if status:
                conds.append("status = ?")
                params.append(status)
            if project_id:
                conds.append("project_id = ?")
                params.append(project_id)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(q, params)
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def update_mission(self, mission_id: str, **kwargs) -> Optional[Dict]:
        allowed_cols = [c for c in self.MISSION_COLUMNS if c in kwargs]
        if not allowed_cols:
            return await self.get_mission(mission_id)
        fields = ", ".join(f"{c} = ?" for c in allowed_cols)
        values = [kwargs[c] for c in allowed_cols] + [mission_id]
        async with self._connect() as db:
            await db.execute(
                f"UPDATE missions SET {fields} WHERE id = ?",
                values,
            )
            await db.commit()
        return await self.get_mission(mission_id)

    async def update_mission_full(self, mission_id: str, row: Dict) -> Optional[Dict]:
        """Persist the full mission row (whitelisted). Used by MissionController."""
        import json as _json
        # Build SET clause from whitelisted columns
        allowed = self.MISSION_COLUMNS
        sets: List[str] = []
        vals: List = []
        for col in allowed:
            if col in row:
                v = row[col]
                if col in ("intent", "plan", "agents", "tools", "progress", "errors", "validation", "result", "execution_log") and not isinstance(v, str):
                    v = _json.dumps(v, ensure_ascii=False)
                sets.append(f"{col} = ?")
                vals.append(v)
        if not sets:
            return await self.get_mission(mission_id)
        vals.append(mission_id)
        async with self._connect() as db:
            await db.execute(
                f"UPDATE missions SET {', '.join(sets)} WHERE id = ?",
                vals,
            )
            await db.commit()
        return await self.get_mission(mission_id)

    async def delete_mission(self, mission_id: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute("SELECT id FROM missions WHERE id = ?", (mission_id,))
            if not await cursor.fetchone():
                return False
            await db.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
            await db.commit()
        return True

    async def append_mission_log(self, mission_id: str, entry: Dict) -> None:
        """Append one entry to the mission's execution_log and persist."""
        import json as _json
        existing = await self.get_mission(mission_id)
        if not existing:
            return
        log = existing.get("execution_log") or []
        if isinstance(log, str):
            try:
                log = _json.loads(log)
            except Exception:
                log = []
        if "ts" not in entry:
            from datetime import datetime
            entry["ts"] = datetime.utcnow().isoformat()
        log.append(entry)
        await self.update_mission(mission_id, execution_log=_json.dumps(log, ensure_ascii=False))

    # --- Projects ---

    async def create_project(
        self,
        project_id: str,
        name: str,
        path: str,
        description: str = "",
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO projects (id, name, path, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name, path, description, now, now),
            )
            await db.commit()
        return {"id": project_id, "name": name, "path": path, "description": description, "created_at": now}

    async def get_projects(self, archived: bool = False) -> List[Dict]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT p.id, p.name, p.path, p.description, p.is_active, p.is_archived, p.created_at, "
                "COUNT(DISTINCT s.id) as session_count, COUNT(DISTINCT c.id) as conversation_count "
                "FROM projects p "
                "LEFT JOIN project_sessions s ON p.id = s.project_id "
                "LEFT JOIN conversations c ON p.id = c.project_id "
                "WHERE p.is_archived = ? "
                "GROUP BY p.id ORDER BY p.updated_at DESC",
                (1 if archived else 0,)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def get_active_project(self) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM projects WHERE is_active = 1 LIMIT 1")
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def activate_project(self, project_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("UPDATE projects SET is_active = 0")
            await db.execute("UPDATE projects SET is_active = 1 WHERE id = ?", (project_id,))
            await db.commit()
        return True

    async def archive_project(self, project_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE projects SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            await db.commit()
        return True

    async def unarchive_project(self, project_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE projects SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            await db.commit()
        return True

    async def delete_project(self, project_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("DELETE FROM project_sessions WHERE project_id = ?", (project_id,))
            await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            await db.commit()
        return True

    async def update_project(self, project_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = self._whitelist_columns(ALLOWED_PROJECT_COLUMNS, kwargs, "projects")
        values = list(kwargs.values()) + [now, project_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE projects SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    # --- Project Sessions ---

    async def create_session(
        self,
        session_id: str,
        project_id: str,
        name: str = "جلسة جديدة",
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO project_sessions (id, project_id, name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, project_id, name, now, now),
            )
            await db.commit()
        return {"id": session_id, "project_id": project_id, "name": name, "created_at": now}

    async def get_sessions(self, project_id: str, archived: bool = False) -> List[Dict]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT s.id, s.name, s.is_active, s.is_archived, s.created_at, "
                "COUNT(DISTINCT c.id) as conversation_count "
                "FROM project_sessions s "
                "LEFT JOIN conversations c ON s.id = c.session_id "
                "WHERE s.project_id = ? AND s.is_archived = ? "
                "GROUP BY s.id ORDER BY s.updated_at DESC",
                (project_id, 1 if archived else 0)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def activate_session(self, session_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("UPDATE project_sessions SET is_active = 0")
            await db.execute("UPDATE project_sessions SET is_active = 1 WHERE id = ?", (session_id,))
            await db.commit()
        return True

    async def archive_session(self, session_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE project_sessions SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()
        return True

    async def unarchive_session(self, session_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE project_sessions SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()
        return True

    async def delete_session(self, session_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("DELETE FROM project_sessions WHERE id = ?", (session_id,))
            await db.commit()
        return True

    async def update_session(self, session_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = self._whitelist_columns(ALLOWED_SESSION_COLUMNS, kwargs, "sessions")
        values = list(kwargs.values()) + [now, session_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE project_sessions SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    # --- Conversations ---

    async def create_conversation(
        self,
        conv_id: str,
        name: str = "محادثة جديدة",
        user_id: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO conversations (id, name, user_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, name, user_id, now, now),
            )
            await db.commit()
        return {"id": conv_id, "name": name, "created_at": now}

    async def get_conversations(self, archived: bool = False) -> List[Dict]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT c.id, c.name, c.is_active, c.is_archived, c.created_at, "
                "COUNT(m.id) as message_count "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "WHERE c.is_archived = ? "
                "GROUP BY c.id ORDER BY c.updated_at DESC",
                (1 if archived else 0,)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def activate_conversation(self, conv_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("UPDATE conversations SET is_active = 0")
            await db.execute(
                "UPDATE conversations SET is_active = 1 WHERE id = ?",
                (conv_id,),
            )
            await db.commit()
        return True

    async def update_conversation_name(self, conv_id: str, name: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?",
                (name, now, conv_id),
            )
            await db.commit()
        return True

    async def update_conversation(self, conv_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = self._whitelist_columns(ALLOWED_CONVERSATION_COLUMNS, kwargs, "conversations")
        values = list(kwargs.values()) + [now, conv_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE conversations SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    async def archive_conversation(self, conv_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE conversations SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            await db.commit()
        return True

    async def unarchive_conversation(self, conv_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "UPDATE conversations SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            await db.commit()
        return True

    async def delete_conversation(self, conv_id: str) -> bool:
        async with self._connect() as db:
            await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            await db.commit()
        return True

    # --- Messages ---

    async def add_message(
        self,
        msg_id: str,
        conversation_id: str,
        role: str,
        content: str,
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
        file_size: Optional[int] = None,
        file_base64: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, file_name, file_type, file_size, file_base64, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, file_name, file_type, file_size, file_base64, now),
            )
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            await db.commit()
        return {"id": msg_id, "role": role, "content": content, "created_at": now}

    async def get_messages(self, conversation_id: str) -> List[Dict]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    # --- Users ---

    async def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, password_hash, now, now),
            )
            await db.commit()
        return {"id": user_id, "username": username, "created_at": now}

    async def get_user(self, username: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def get_users_count(self) -> int:
        async with self._connect() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            row = await cursor.fetchone()
        return row[0] if row else 0

    # --- Audit Logs ---

    async def log_action(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                "INSERT INTO audit_logs (user_id, action, resource, details, ip_address) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, action, resource, details, ip_address),
            )
            await db.commit()

    # --- Helpers ---

    @staticmethod
    def _row_to_dict(row: tuple, description: list) -> Dict:
        return {desc[0]: value for desc, value in zip(description, row)}

    # --- Provider Keys (multi-key per provider, round-robin) ---

    async def add_provider_key(
        self,
        provider: str,
        key_value: str,
        nickname: str,
    ) -> Dict:
        """Insert a new provider key. Returns the created row.

        Raises ``ValueError`` if a key with the same nickname already exists
        for this provider (active or not).
        """
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM provider_keys WHERE provider = ?",
                (provider,),
            )
            row = await cur.fetchone()
            sort_order = (row[0] if row else 0)
            try:
                cur = await db.execute(
                    "INSERT INTO provider_keys (provider, key_value, nickname, sort_order, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (provider, key_value, nickname, sort_order, now),
                )
                key_id = cur.lastrowid
            except Exception as e:
                msg = str(e)
                if "UNIQUE" in msg or "idx_provider_keys_nickname" in msg:
                    raise ValueError(
                        f"A key named '{nickname}' already exists for {provider}."
                    ) from e
                raise
            await db.commit()
        return await self.get_provider_key(key_id)

    async def get_provider_key(self, key_id: int) -> Optional[Dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM provider_keys WHERE id = ?",
                (key_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            raw = d.get("key_value", "")
            d["key_masked"] = self._mask_key(raw)
            if d.get("models_cache_json"):
                try:
                    d["models"] = json.loads(d["models_cache_json"])
                except Exception:
                    d["models"] = []
            else:
                d["models"] = []
            d.pop("key_value", None)
            return d

    @staticmethod
    def _mask_key(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "…" + value[-4:]

    async def _fetch_provider_key_row(self, key_id: int) -> Optional[Dict]:
        """Internal: fetch the full row including the raw ``key_value``."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM provider_keys WHERE id = ?",
                (key_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("models_cache_json"):
                try:
                    d["models"] = json.loads(d["models_cache_json"])
                except Exception:
                    d["models"] = []
            else:
                d["models"] = []
            return d

    async def list_provider_keys(
        self,
        provider: Optional[str] = None,
        include_disabled: bool = False,
    ) -> List[Dict]:
        """List keys, newest first (by ``id`` ASC). Use ``sort_order`` for round-robin."""
        where = []
        params: list = []
        if provider:
            where.append("provider = ?")
            params.append(provider)
        if not include_disabled:
            where.append("is_enabled = 1")
        sql = "SELECT * FROM provider_keys"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY provider ASC, sort_order ASC, id ASC"
        out: List[Dict] = []
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            for row in rows:
                d = dict(row)
                if d.get("models_cache_json"):
                    try:
                        d["models"] = json.loads(d["models_cache_json"])
                    except Exception:
                        d["models"] = []
                else:
                    d["models"] = []
                raw = d.get("key_value", "")
                d["key_masked"] = self._mask_key(raw)
                d.pop("key_value", None)
                out.append(d)
        return out

    async def update_provider_key(self, key_id: int, **kwargs) -> bool:
        """Update whitelisted fields. Allowed: nickname, is_active, is_enabled, sort_order."""
        allowed = {
            "nickname", "is_active", "is_enabled", "sort_order",
        }
        bad = [k for k in kwargs if k not in allowed]
        if bad:
            raise ValueError(f"Disallowed field(s): {bad}")
        if not kwargs:
            return True
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [key_id]
        async with self._connect() as db:
            await db.execute(
                f"UPDATE provider_keys SET {fields} WHERE id = ?",
                values,
            )
            await db.commit()
        return True

    async def delete_provider_key(self, key_id: int) -> bool:
        async with self._connect() as db:
            await db.execute("DELETE FROM provider_keys WHERE id = ?", (key_id,))
            await db.commit()
        return True

    async def set_active_provider_key(self, provider: str, key_id: int) -> bool:
        """Mark ``key_id`` as the active key for ``provider`` and clear others."""
        async with self._connect() as db:
            await db.execute(
                "UPDATE provider_keys SET is_active = 0 WHERE provider = ?",
                (provider,),
            )
            await db.execute(
                "UPDATE provider_keys SET is_active = 1 WHERE id = ? AND provider = ?",
                (key_id, provider),
            )
            await db.commit()
        return True

    async def mark_provider_key_tested(
        self,
        key_id: int,
        status: str,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
        models: Optional[list] = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            if models is not None:
                models_json = json.dumps(models, ensure_ascii=False)
                await db.execute(
                    "UPDATE provider_keys SET status = ?, last_test_at = ?, "
                    "last_test_latency_ms = ?, last_test_error = ?, "
                    "models_cache_json = ?, models_cached_at = ? WHERE id = ?",
                    (status, now, latency_ms, error, models_json, now, key_id),
                )
            else:
                await db.execute(
                    "UPDATE provider_keys SET status = ?, last_test_at = ?, "
                    "last_test_latency_ms = ?, last_test_error = ? WHERE id = ?",
                    (status, now, latency_ms, error, key_id),
                )
            await db.commit()

    async def get_active_provider_key(self, provider: str) -> Optional[Dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM provider_keys "
                "WHERE provider = ? AND is_active = 1 AND is_enabled = 1 "
                "LIMIT 1",
                (provider,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def next_round_robin_key(self, provider: str) -> Optional[Dict]:
        """Pick the next enabled key for ``provider`` in round-robin order.

        Uses the MAX of ``rotation_index`` across all keys of this provider
        as the monotonic counter. The chosen key has its ``rotation_index``
        set to ``max_idx + 1`` so it never wins twice in a row. (Note: when
        keys share the same max, the one with lowest id wins first; this is
        deterministic but may briefly favor a key. Acceptable for our use
        case — for strict round-robin, a separate counter table would be
        needed.)
        """
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM provider_keys "
                "WHERE provider = ? AND is_enabled = 1 "
                "ORDER BY sort_order ASC, id ASC",
                (provider,),
            )
            rows = await cur.fetchall()
            if not rows:
                return None
            keys = [dict(r) for r in rows]
            valid = [k for k in keys if k.get("status") not in ("invalid", "error")]
            pool = valid or keys
            if not pool:
                return None
            cur = await db.execute(
                "SELECT COALESCE(MAX(rotation_index), 0) FROM provider_keys WHERE provider = ?",
                (provider,),
            )
            r = await cur.fetchone()
            max_idx = (r[0] if r else 0)
            # New index = max+1
            new_idx = max_idx + 1
            # Pick the key with the smallest rotation_index (oldest picked)
            # Tie-break by sort_order then id (stable)
            pool_sorted = sorted(
                pool,
                key=lambda k: (k.get("rotation_index", 0), k.get("sort_order", 0), k["id"]),
            )
            chosen = pool_sorted[0]
            await db.execute(
                "UPDATE provider_keys SET rotation_index = ? WHERE id = ?",
                (new_idx, chosen["id"]),
            )
            await db.commit()
            return chosen

    # ── v1.1 Phase 5: Industrial Control Plane ────────────────────────

    # --- Organizations ---

    async def create_organization(
        self,
        org_id: str,
        name: str,
        sector: str = "enterprise_it",
        region: str = "global",
        compliance_profile: str = "none",
        policy_id: str = "default",
        deployment_profile: str = "development",
        status: str = "active",
        config: str = "{}",
        metadata: str = "{}",
    ) -> Dict:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO enterprise_orgs
                (id, name, sector, region, compliance_profile, policy_id, deployment_profile, status, config, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (org_id, name, sector, region, compliance_profile, policy_id, deployment_profile, status, config, metadata),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM enterprise_orgs WHERE id = ?", (org_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def get_organization(self, org_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM enterprise_orgs WHERE id = ?", (org_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else None

    async def list_organizations(self, status: Optional[str] = None, sector: Optional[str] = None) -> List[Dict]:
        async with self._connect() as db:
            if status and sector:
                cursor = await db.execute("SELECT * FROM enterprise_orgs WHERE status = ? AND sector = ?", (status, sector))
            elif status:
                cursor = await db.execute("SELECT * FROM enterprise_orgs WHERE status = ?", (status,))
            elif sector:
                cursor = await db.execute("SELECT * FROM enterprise_orgs WHERE sector = ?", (sector,))
            else:
                cursor = await db.execute("SELECT * FROM enterprise_orgs")
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def update_organization(self, org_id: str, **kwargs) -> Optional[Dict]:
        allowed = {"name", "sector", "region", "compliance_profile", "policy_id", "deployment_profile", "status", "config", "metadata"}
        sets = self._whitelist_columns(allowed, kwargs, "enterprise_orgs")
        if not sets:
            return await self.get_organization(org_id)
        values = list(kwargs.values()) + [org_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE enterprise_orgs SET {sets} WHERE id = ?", values)
            await db.commit()
        return await self.get_organization(org_id)

    async def delete_organization(self, org_id: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute("DELETE FROM enterprise_orgs WHERE id = ?", (org_id,))
            await db.commit()
            return cursor.rowcount > 0

    # --- Enterprise Users ---

    async def create_enterprise_user(
        self,
        user_id: str,
        email: str,
        organization_id: str,
        display_name: str = "",
        role: str = "viewer",
        status: str = "invited",
        mfa_enabled: int = 0,
        department: str = "",
        scopes: str = "",
        metadata: str = "{}",
    ) -> Dict:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO enterprise_users
                (id, email, organization_id, display_name, role, status, mfa_enabled, department, scopes, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, email, organization_id, display_name, role, status, mfa_enabled, department, scopes, metadata),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM enterprise_users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def get_enterprise_user(self, user_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM enterprise_users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else None

    async def get_enterprise_user_by_email(self, email: str, organization_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM enterprise_users WHERE email = ? AND organization_id = ?", (email, organization_id))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else None

    async def list_enterprise_users(self, organization_id: Optional[str] = None, role: Optional[str] = None) -> List[Dict]:
        async with self._connect() as db:
            if organization_id and role:
                cursor = await db.execute("SELECT * FROM enterprise_users WHERE organization_id = ? AND role = ?", (organization_id, role))
            elif organization_id:
                cursor = await db.execute("SELECT * FROM enterprise_users WHERE organization_id = ?", (organization_id,))
            elif role:
                cursor = await db.execute("SELECT * FROM enterprise_users WHERE role = ?", (role,))
            else:
                cursor = await db.execute("SELECT * FROM enterprise_users")
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def update_enterprise_user(self, user_id: str, **kwargs) -> Optional[Dict]:
        allowed = {"email", "organization_id", "display_name", "role", "status", "mfa_enabled", "department", "scopes", "metadata", "last_login_at"}
        sets = self._whitelist_columns(allowed, kwargs, "enterprise_users")
        if not sets:
            return await self.get_enterprise_user(user_id)
        values = list(kwargs.values()) + [user_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE enterprise_users SET {sets} WHERE id = ?", values)
            await db.commit()
        return await self.get_enterprise_user(user_id)

    async def delete_enterprise_user(self, user_id: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute("DELETE FROM enterprise_users WHERE id = ?", (user_id,))
            await db.commit()
            return cursor.rowcount > 0

    # --- Enterprise Policies ---

    async def create_enterprise_policy(
        self,
        policy_id: str,
        name: str,
        organization_id: str,
        description: str = "",
        allowed_tools: str = "",
        blocked_tools: str = "",
        approval_required_for: str = "",
        max_timeout_s: int = 60,
        max_memory_mb: int = 256,
        max_calls_per_mission: int = 100,
        max_concurrent_missions: int = 5,
        require_mfa_for: str = "",
        deny_after_hours: int = 0,
        allowed_hours: str = "{}",
        active: int = 1,
        metadata: str = "{}",
    ) -> Dict:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO enterprise_policies
                (id, name, organization_id, description, allowed_tools, blocked_tools, approval_required_for,
                 max_timeout_s, max_memory_mb, max_calls_per_mission, max_concurrent_missions,
                 require_mfa_for, deny_after_hours, allowed_hours, active, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (policy_id, name, organization_id, description, allowed_tools, blocked_tools, approval_required_for,
                 max_timeout_s, max_memory_mb, max_calls_per_mission, max_concurrent_missions,
                 require_mfa_for, deny_after_hours, allowed_hours, active, metadata),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM enterprise_policies WHERE id = ?", (policy_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def get_enterprise_policy(self, policy_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            cursor = await db.execute("SELECT * FROM enterprise_policies WHERE id = ?", (policy_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else None

    async def list_enterprise_policies(self, organization_id: Optional[str] = None) -> List[Dict]:
        async with self._connect() as db:
            if organization_id:
                cursor = await db.execute("SELECT * FROM enterprise_policies WHERE organization_id = ?", (organization_id,))
            else:
                cursor = await db.execute("SELECT * FROM enterprise_policies")
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def update_enterprise_policy(self, policy_id: str, **kwargs) -> Optional[Dict]:
        allowed = {"name", "description", "allowed_tools", "blocked_tools", "approval_required_for",
                   "max_timeout_s", "max_memory_mb", "max_calls_per_mission", "max_concurrent_missions",
                   "require_mfa_for", "deny_after_hours", "allowed_hours", "active", "metadata"}
        sets = self._whitelist_columns(allowed, kwargs, "enterprise_policies")
        if not sets:
            return await self.get_enterprise_policy(policy_id)
        values = list(kwargs.values()) + [policy_id]
        async with self._connect() as db:
            await db.execute(f"UPDATE enterprise_policies SET {sets} WHERE id = ?", values)
            await db.commit()
        return await self.get_enterprise_policy(policy_id)

    async def delete_enterprise_policy(self, policy_id: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute("DELETE FROM enterprise_policies WHERE id = ?", (policy_id,))
            await db.commit()
            return cursor.rowcount > 0

    # --- Enterprise Audit ---

    async def create_enterprise_audit(
        self,
        entry_id: str,
        action: str,
        who: str = "system",
        user_email: str = "",
        user_role: str = "",
        org_id: str = "",
        agent_id: str = "",
        tool: str = "",
        subject: str = "",
        result: str = "ok",
        approval_id: str = "",
        severity: str = "LOW",
        deployment: str = "development",
        context: str = "{}",
        ts: str = "",
    ) -> Dict:
        if not ts:
            from datetime import datetime as _dt
            ts = _dt.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO enterprise_audit
                (id, action, who, user_email, user_role, org_id, agent_id, tool, subject, result, approval_id, severity, deployment, context, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, action, who, user_email, user_role, org_id, agent_id, tool, subject, result, approval_id, severity, deployment, context, ts),
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM enterprise_audit WHERE id = ?", (entry_id,))
            row = await cursor.fetchone()
        return self._row_to_dict(row, cursor.description) if row else {}

    async def list_enterprise_audit(
        self,
        who: Optional[str] = None,
        org_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        action: Optional[str] = None,
        tool: Optional[str] = None,
        severity: Optional[str] = None,
        result: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        where = []
        params: List = []
        if who: where.append("who = ?"); params.append(who)
        if org_id: where.append("org_id = ?"); params.append(org_id)
        if agent_id: where.append("agent_id = ?"); params.append(agent_id)
        if action: where.append("action = ?"); params.append(action)
        if tool: where.append("tool = ?"); params.append(tool)
        if severity: where.append("severity = ?"); params.append(severity)
        if result: where.append("result = ?"); params.append(result)
        if since: where.append("ts >= ?"); params.append(since)
        if until: where.append("ts <= ?"); params.append(until)
        where_sql = " WHERE " + " AND ".join(where) if where else ""
        params.append(limit)
        async with self._connect() as db:
            cursor = await db.execute(
                f"SELECT * FROM enterprise_audit{where_sql} ORDER BY ts DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def count_enterprise_audit(self, org_id: Optional[str] = None) -> int:
        async with self._connect() as db:
            if org_id:
                cursor = await db.execute("SELECT COUNT(*) FROM enterprise_audit WHERE org_id = ?", (org_id,))
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM enterprise_audit")
            row = await cursor.fetchone()
        return row[0] if row else 0

    # ════════════════════════════════════════════════════════════════════════════
    # SKILLS (RC12.4 — Skill Evolution Layer)
    # ════════════════════════════════════════════════════════════════════════════

    _SKILL_JSON_FIELDS = frozenset({
        "required_tools", "required_models", "required_permissions",
        "input_schema", "output_schema", "metadata",
    })

    ALLOWED_SKILL_COLUMNS = frozenset({
        "name", "description", "version", "owner_agent", "category",
        "required_tools", "required_models", "required_permissions",
        "input_schema", "output_schema", "success_rate", "failure_rate",
        "usage_count", "avg_execution_time", "best_agent", "best_model",
        "created_from_mission", "status", "approval_state",
        "approval_by", "approval_at", "metadata",
    })

    async def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        owner_agent: str = "",
        category: str = "general",
        required_tools: List = None,
        required_models: List = None,
        required_permissions: List = None,
        input_schema: Dict = None,
        output_schema: Dict = None,
        created_from_mission: str = "",
        status: str = "discovered",
        metadata: Dict = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO skills
                (id, name, description, version, owner_agent, category,
                 required_tools, required_models, required_permissions,
                 input_schema, output_schema, created_from_mission,
                 status, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill_id, name, description, version, owner_agent, category,
                    json.dumps(required_tools or [], ensure_ascii=False),
                    json.dumps(required_models or [], ensure_ascii=False),
                    json.dumps(required_permissions or [], ensure_ascii=False),
                    json.dumps(input_schema or {}, ensure_ascii=False),
                    json.dumps(output_schema or {}, ensure_ascii=False),
                    created_from_mission, status,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now, now,
                ),
            )
            await db.commit()
        # Auto-create initial version
        await self.create_skill_version(skill_id, version, created_by=owner_agent)
        return await self.get_skill(skill_id)

    async def get_skill(self, skill_id: str) -> Optional[Dict]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
            row = await cursor.fetchone()
        return self._decode_row(row, json_fields=self._SKILL_JSON_FIELDS) if row else None

    async def list_skills(
        self,
        status: Optional[str] = None,
        owner_agent: Optional[str] = None,
        category: Optional[str] = None,
        approval_state: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        clauses = []
        params: List = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if owner_agent:
            clauses.append("owner_agent = ?")
            params.append(owner_agent)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if approval_state:
            clauses.append("approval_state = ?")
            params.append(approval_state)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM skills{where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()
        return [self._decode_row(r, json_fields=self._SKILL_JSON_FIELDS) for r in rows]

    async def update_skill(self, skill_id: str, **kwargs) -> Optional[Dict]:
        allowed = self.ALLOWED_SKILL_COLUMNS
        json_encode_fields = {"required_tools", "required_models", "required_permissions",
                              "input_schema", "output_schema", "metadata"}
        sets: List[str] = []
        vals: List = []
        for col in allowed:
            if col in kwargs:
                v = kwargs[col]
                if col in json_encode_fields and not isinstance(v, str):
                    v = json.dumps(v, ensure_ascii=False)
                sets.append(f"{col} = ?")
                vals.append(v)
        if not sets:
            return await self.get_skill(skill_id)
        sets.append("updated_at = ?")
        vals.append(datetime.utcnow().isoformat())
        vals.append(skill_id)
        async with self._connect() as db:
            await db.execute(
                f"UPDATE skills SET {', '.join(sets)} WHERE id = ?",
                vals,
            )
            await db.commit()
        return await self.get_skill(skill_id)

    async def delete_skill(self, skill_id: str) -> bool:
        async with self._connect() as db:
            cursor = await db.execute("SELECT id FROM skills WHERE id = ?", (skill_id,))
            if not await cursor.fetchone():
                return False
            await db.execute("DELETE FROM skill_execution_history WHERE skill_id = ?", (skill_id,))
            await db.execute("DELETE FROM skill_versions WHERE skill_id = ?", (skill_id,))
            await db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            await db.commit()
        return True

    async def count_skills(self, status: Optional[str] = None) -> int:
        async with self._connect() as db:
            if status:
                cursor = await db.execute("SELECT COUNT(*) FROM skills WHERE status = ?", (status,))
            else:
                cursor = await db.execute("SELECT COUNT(*) FROM skills")
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def increment_skill_usage(
        self, skill_id: str, success: bool, execution_time: float = 0.0,
        mission_id: str = "", agent_id: str = "", cost: float = 0.0, error: str = "",
    ) -> Optional[Dict]:
        """Increment usage count, update rates, and record execution history."""
        skill = await self.get_skill(skill_id)
        if not skill:
            return None
        old_count = skill.get("usage_count", 0)
        old_success = skill.get("success_rate", 0.0)
        new_count = old_count + 1
        if success:
            new_success_rate = ((old_success * old_count) + 1.0) / new_count
        else:
            new_success_rate = (old_success * old_count) / new_count
        new_failure_rate = 1.0 - new_success_rate
        old_avg = skill.get("avg_execution_time", 0.0)
        new_avg = ((old_avg * old_count) + execution_time) / new_count if new_count > 0 else execution_time
        updated = await self.update_skill(
            skill_id,
            usage_count=new_count,
            success_rate=new_success_rate,
            failure_rate=new_failure_rate,
            avg_execution_time=new_avg,
        )
        # Record execution in separate table
        await self.record_skill_execution(
            skill_id=skill_id, success=success, duration=execution_time,
            mission_id=mission_id, agent_id=agent_id, cost=cost, error=error,
        )
        return updated

    # ── Skill Execution History (RC12.4.1) ───────────────────────────────────

    async def record_skill_execution(
        self,
        skill_id: str,
        success: bool = True,
        duration: float = 0.0,
        mission_id: str = "",
        agent_id: str = "",
        cost: float = 0.0,
        error: str = "",
        metadata: Dict = None,
    ) -> Dict:
        """Record a single execution event for a skill."""
        entry_id = f"seh_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO skill_execution_history
                (id, skill_id, mission_id, agent_id, success, duration,
                 cost, error, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id, skill_id, mission_id, agent_id,
                    1 if success else 0, duration, cost, error,
                    json.dumps(metadata or {}, ensure_ascii=False), now,
                ),
            )
            await db.commit()
        return {"id": entry_id, "skill_id": skill_id, "created_at": now}

    async def get_skill_history(
        self, skill_id: str, limit: int = 100
    ) -> List[Dict]:
        """Get execution history for a skill (newest first)."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM skill_execution_history WHERE skill_id = ? ORDER BY created_at DESC LIMIT ?",
                (skill_id, limit),
            )
            rows = await cursor.fetchall()
        return [self._decode_row(r, json_fields={"metadata"}) for r in rows]

    async def count_skill_executions(self, skill_id: str) -> int:
        async with self._connect() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM skill_execution_history WHERE skill_id = ?", (skill_id,)
            )
            row = await cursor.fetchone()
        return row[0] if row else 0

    # ── Skill Versions (RC12.4.1) ───────────────────────────────────────────

    async def create_skill_version(
        self,
        skill_id: str,
        version: str,
        config: Dict = None,
        created_by: str = "",
    ) -> Dict:
        """Create an immutable version snapshot of a skill."""
        ver_id = f"sv_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO skill_versions
                (id, skill_id, version, config, created_at, created_by, approved_by)
                VALUES (?, ?, ?, ?, ?, ?, '')""",
                (
                    ver_id, skill_id, version,
                    json.dumps(config or {}, ensure_ascii=False), now, created_by,
                ),
            )
            await db.commit()
        return {"id": ver_id, "skill_id": skill_id, "version": version, "created_at": now}

    async def get_skill_versions(self, skill_id: str) -> List[Dict]:
        """Get all versions for a skill (newest first)."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM skill_versions WHERE skill_id = ? ORDER BY created_at DESC",
                (skill_id,),
            )
            rows = await cursor.fetchall()
        return [self._decode_row(r, json_fields={"config"}) for r in rows]

    async def approve_skill_version(
        self, version_id: str, approved_by: str
    ) -> Optional[Dict]:
        """Approve a skill version."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM skill_versions WHERE id = ?", (version_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            await db.execute(
                "UPDATE skill_versions SET approved_by = ? WHERE id = ?",
                (approved_by, version_id),
            )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM skill_versions WHERE id = ?", (version_id,)
            )
            row = await cursor.fetchone()
        return self._decode_row(row, json_fields={"config"}) if row else None


db = Database()
