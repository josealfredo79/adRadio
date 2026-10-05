"""Descubre negocios (/mi): users.directory_listed — el negocio aparece en el
directorio de IaRadio (encendido por defecto: su página pública ya lo es);
contacts.source 'directory' para quien se une desde ahí.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-04
"""
import sqlalchemy as sa

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("directory_listed", sa.Boolean(), nullable=False, server_default="true"))
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_source",
        "contacts",
        "source IN ('manual','csv','landing','referral','widget','qr','directory')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint(
        "ck_contacts_source",
        "contacts",
        "source IN ('manual','csv','landing','referral','widget','qr')",
    )
    op.drop_column("users", "directory_listed")
