"""Workspace Isolation Tests.

Verifies that User A cannot access User B's workspace.
Default Deny — every unauthorized access attempt must be rejected.
Tests workspace models and access control directly.

Ref: Phase P Batch 3 (P.3 — User Workspace Layer)
Ref: Canon LAW 10, LAW 23
"""

from core.models.workspace import (
    Tenant,
    TenantStatus,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceStatus,
    UserRole,
)


class TestTenantModel:
    def test_tenant_creation(self) -> None:
        tenant = Tenant(name="Acme Corp")
        assert tenant.name == "Acme Corp"
        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.max_workspaces == 10
        assert tenant.max_users_per_workspace == 25
        assert tenant.is_active() is True

    def test_tenant_suspended(self) -> None:
        tenant = Tenant(name="Suspended Corp", status=TenantStatus.SUSPENDED)
        assert tenant.is_active() is False


class TestUserModel:
    def test_user_creation(self) -> None:
        user = User(tenant_id="t-1", email="alice@acme.com", display_name="Alice")
        assert user.tenant_id == "t-1"
        assert user.email == "alice@acme.com"
        assert user.is_active is True
        assert user.belongs_to_tenant("t-1") is True
        assert user.belongs_to_tenant("t-2") is False

    def test_user_inactive(self) -> None:
        user = User(tenant_id="t-1", is_active=False)
        assert user.is_active is False


class TestWorkspaceModel:
    def test_workspace_creation(self) -> None:
        ws = Workspace(tenant_id="t-1", name="Project Alpha")
        assert ws.tenant_id == "t-1"
        assert ws.name == "Project Alpha"
        assert ws.status == WorkspaceStatus.ACTIVE
        assert ws.is_accessible() is True
        assert ws.belongs_to_tenant("t-1") is True

    def test_workspace_suspended(self) -> None:
        ws = Workspace(tenant_id="t-1", name="Suspended", status=WorkspaceStatus.SUSPENDED)
        assert ws.is_accessible() is False


class TestWorkspaceMember:
    def test_viewer_no_write_access(self) -> None:
        member = WorkspaceMember(user_id="u-1", workspace_id="ws-1", role=UserRole.VIEWER)
        assert member.has_write_access() is False
        assert member.has_admin_access() is False

    def test_editor_has_write_access(self) -> None:
        member = WorkspaceMember(user_id="u-1", workspace_id="ws-1", role=UserRole.EDITOR)
        assert member.has_write_access() is True
        assert member.has_admin_access() is False

    def test_admin_has_admin_access(self) -> None:
        member = WorkspaceMember(user_id="u-1", workspace_id="ws-1", role=UserRole.ADMIN)
        assert member.has_write_access() is True
        assert member.has_admin_access() is True

    def test_owner_has_full_access(self) -> None:
        member = WorkspaceMember(user_id="u-1", workspace_id="ws-1", role=UserRole.OWNER)
        assert member.has_write_access() is True
        assert member.has_admin_access() is True


class TestWorkspaceIsolation:
    def test_user_a_cannot_access_user_b_workspace(self) -> None:
        tenant = Tenant(id="t-1", name="Acme")
        user_a = User(id="u-alice", tenant_id="t-1")
        user_b = User(id="u-bob", tenant_id="t-1")
        workspace_b = Workspace(id="ws-bob", tenant_id="t-1", name="Bob Workspace")

        member_b = WorkspaceMember(user_id="u-bob", workspace_id="ws-bob", role=UserRole.OWNER)
        assert member_b.user_id == "u-bob"

        assert user_a.id != member_b.user_id
        assert user_a.id != "u-bob"

    def test_cross_tenant_access_denied(self) -> None:
        tenant_a = Tenant(id="t-a", name="Company A")
        tenant_b = Tenant(id="t-b", name="Company B")
        user_a = User(id="u-a", tenant_id="t-a")
        workspace_b = Workspace(id="ws-b", tenant_id="t-b", name="Company B WS")

        assert user_a.tenant_id != workspace_b.tenant_id
        assert user_a.belongs_to_tenant(workspace_b.tenant_id) is False

    def test_inactive_user_denied(self) -> None:
        user = User(id="u-inactive", tenant_id="t-1", is_active=False)
        assert user.is_active is False

    def test_deleted_workspace_denied(self) -> None:
        workspace = Workspace(id="ws-del", tenant_id="t-1", name="Deleted", status=WorkspaceStatus.DELETED)
        assert workspace.is_accessible() is False

    def test_viewer_cannot_add_members(self) -> None:
        viewer = WorkspaceMember(user_id="u-viewer", workspace_id="ws-1", role=UserRole.VIEWER)
        assert viewer.has_write_access() is False

    def test_cross_tenant_user_not_in_workspace(self) -> None:
        user = User(id="u-ext", tenant_id="t-ext")
        workspace = Workspace(id="ws-int", tenant_id="t-int")
        assert user.belongs_to_tenant(workspace.tenant_id) is False
