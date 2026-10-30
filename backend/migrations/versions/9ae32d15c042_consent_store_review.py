"""Store permissions, participant consent, session lifecycle and human review.

Revision ID: 9ae32d15c042
Revises: 7965ef7f839d
"""
from alembic import op
import sqlalchemy as sa
from uuid import uuid4
from datetime import datetime, timezone

revision = "9ae32d15c042"
down_revision = "7965ef7f839d"
branch_labels = depends_on = None


def reference(table, name, target, ondelete):
    if op.get_bind().dialect.name == "sqlite":
        op.execute(sa.text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" VARCHAR REFERENCES "{target}" (id) ON DELETE {ondelete}'))
    else:
        op.add_column(table, sa.Column(name, sa.String(), sa.ForeignKey(target + ".id", ondelete=ondelete)))


def upgrade():
    op.add_column("organizations", sa.Column("retention_policy", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("users", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("stores", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_stores_org_id", "stores", ["org_id"])
    op.create_table("store_memberships", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.String(), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "store_id"))
    # Nullable foreign keys are additive on SQLite, avoiding a destructive table rebuild.
    reference("devices", "store_id", "stores", "RESTRICT")
    op.add_column("devices", sa.Column("capabilities", sa.JSON(), nullable=False,
        server_default='{"audio_transfer": true, "remote_controls": false, "recording_indicator": false}'))
    reference("conversations", "store_id", "stores", "RESTRICT")
    reference("conversations", "created_by", "users", "SET NULL")
    for column in [
        sa.Column("purpose", sa.String(500), nullable=False, server_default="Legacy session — consent revalidation required"),
        sa.Column("session_state", sa.String(), nullable=False, server_default="awaiting_consent"),
        sa.Column("consent_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("capture_conditions_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("state_updated_at", sa.String(), nullable=False, server_default=""),
        sa.Column("review_status", sa.String(), nullable=False, server_default="unreviewed"),
    ]:
        op.add_column("conversations", column)
    op.create_index("ix_conversations_store_id", "conversations", ["store_id"])
    op.create_index("ix_conversations_session_state", "conversations", ["session_state"])
    for column in [
        sa.Column("review_status", sa.String(), nullable=False, server_default="unreviewed"),
        sa.Column("reviewed_at", sa.String()),
        sa.Column("evidence_status", sa.String(), nullable=False, server_default="exact_quote"),
        sa.Column("confidence_method", sa.String(), nullable=False, server_default="uncalibrated_model_estimate"),
        sa.Column("impact", sa.Text()), sa.Column("recommendation", sa.Text()),
        sa.Column("success_metric", sa.Text()), sa.Column("priority_rationale", sa.Text()),
    ]:
        op.add_column("insights", column)
    reference("insights", "reviewed_by", "users", "SET NULL")
    op.create_index("ix_insights_review_status", "insights", ["review_status"])
    reference("tasks", "owner_id", "users", "SET NULL")
    op.add_column("tasks", sa.Column("title", sa.String(180), nullable=False, server_default="Suggested follow-up"))
    op.add_column("tasks", sa.Column("deadline_basis", sa.String(), nullable=False, server_default="not_established"))
    op.add_column("tasks", sa.Column("deadline_quote", sa.Text()))
    op.add_column("audit_events", sa.Column("details", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("participant_consents", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_ref", sa.String(80), nullable=False), sa.Column("token_hash", sa.String(), unique=True),
        sa.Column("token_expires_at", sa.String()), sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("notice_version", sa.String(), nullable=False),
        sa.Column("granted_at", sa.String()), sa.Column("withdrawn_at", sa.String()),
        sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_participant_consents_conversation_id", "participant_consents", ["conversation_id"])
    op.create_table("review_events", sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False), sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False), sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False))
    op.create_index("ix_review_events_conversation_id", "review_events", ["conversation_id"])
    connection = op.get_bind()
    timestamp = datetime.now(timezone.utc).isoformat()
    for org in connection.execute(sa.text("SELECT id FROM organizations")).mappings():
        # Preserve the existing organization's bounded retention on upgrade.
        # New organizations use the development defaults from policy_for().
        import json
        from backend.app.config import Settings
        days = Settings().retention_days
        connection.execute(sa.text("UPDATE organizations SET retention_policy=:policy WHERE id=:id"),
            {"policy": json.dumps({"raw_audio_hours": min(days * 24, 720), "transcript_days": days,
                "derived_days": days, "consent_days": days}), "id": org["id"]})
        store_id = str(uuid4())
        connection.execute(sa.text("INSERT INTO stores (id, org_id, name, created_at) VALUES (:id,:org,'Main store',:now)"),
                           {"id":store_id,"org":org["id"],"now":timestamp})
        users = list(connection.execute(sa.text("SELECT id, role FROM users WHERE org_id=:org"), {"org":org["id"]}).mappings())
        owner = next((u["id"] for u in users if u["role"] in {"admin", "owner"}), None)
        for user in users:
            connection.execute(sa.text("INSERT INTO store_memberships (id,user_id,store_id) VALUES (:id,:u,:s)"),
                               {"id":str(uuid4()),"u":user["id"],"s":store_id})
        connection.execute(sa.text("UPDATE conversations SET store_id=:s, created_by=:u, state_updated_at=:now, "
            "session_state=CASE WHEN status='complete' THEN 'needs_review' WHEN status='failed' THEN 'failed' ELSE 'awaiting_consent' END WHERE org_id=:org"),
            {"s":store_id,"u":owner,"org":org["id"],"now":timestamp})
        connection.execute(sa.text("UPDATE devices SET store_id=:s WHERE org_id=:org"), {"s":store_id,"org":org["id"]})
    # Existing operator attestations are preserved, and are never upgraded into participant consent.


def downgrade():
    raise RuntimeError("V1 contains consent and review history. Restore an authorized backup rather than discarding governance records.")
