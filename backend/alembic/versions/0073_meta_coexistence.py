"""Coexistencia de WhatsApp: el negocio conectó el número de su app WhatsApp
Business (lo sigue usando en su celular) en vez de uno nuevo.

- users.meta_coexistence: no se vuelve a registrar el número (Meta lo
  prohíbe en coexistencia) y el Inbox muestra lo que el dueño manda desde su
  celular (docs/specs/2026-10-12-coexistencia.md).
- contacts.source admite 'whatsapp_app': contactos que llegaron de la libreta
  de su app (sin consentimiento confirmado).

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-12
"""
import sqlalchemy as sa

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


_OLD_SOURCES = "'manual','csv','landing','referral','widget','qr','directory'"


def upgrade() -> None:
    op.add_column("users", sa.Column("meta_coexistence", sa.Boolean(), nullable=False, server_default="false"))
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint("ck_contacts_source", "contacts", f"source IN ({_OLD_SOURCES},'whatsapp_app')")


def downgrade() -> None:
    op.execute("UPDATE contacts SET source = 'manual' WHERE source = 'whatsapp_app'")
    op.drop_constraint("ck_contacts_source", "contacts", type_="check")
    op.create_check_constraint("ck_contacts_source", "contacts", f"source IN ({_OLD_SOURCES})")
    op.drop_column("users", "meta_coexistence")
