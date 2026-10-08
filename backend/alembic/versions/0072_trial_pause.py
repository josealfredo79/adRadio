"""Fin de la prueba: pausa automática y +5 días si se está usando.

- users.billing_exempt: nunca se pausa (cuenta de IaRadio, demos @iaradio.app, admins).
- users.trial_extended_at: cuándo se dieron los 5 días extra (una sola vez).
- users.last_seen_at: última vez que el dueño abrió su panel.

Hasta ahora las pruebas nunca vencían (cleanup_expired_data solo tocaba
cuentas "active"). Para no pausar a nadie de golpe, las pruebas que ya
vencieron o vencen en menos de 15 días reciben 15 días desde hoy.

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-08
"""
import sqlalchemy as sa

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("billing_exempt", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("trial_extended_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE users SET billing_exempt = true "
        "WHERE email = 'tecnologicotlaxiaco@gmail.com' OR email LIKE '%@iaradio.app' OR role = 'admin'"
    )
    op.execute(
        "UPDATE users SET plan_expires_at = now() + interval '15 days' "
        "WHERE subscription_status = 'trial' AND billing_exempt = false "
        "AND plan_expires_at IS NOT NULL AND plan_expires_at < now() + interval '15 days'"
    )


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "trial_extended_at")
    op.drop_column("users", "billing_exempt")
