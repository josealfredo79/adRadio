"""Fotos y "Sobre nosotros" de la página pública del negocio (/sitio/{slug}).

- users.site_photos: URLs (en orden) de las fotos que sube el dueño para el
  carrusel de la portada. Null/vacío = se usan fotos de stock de su giro.
- users.site_about: texto de "Sobre nosotros" que escribe el dueño.

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("site_photos", postgresql.JSONB(), nullable=True))
    op.add_column("users", sa.Column("site_about", sa.String(600), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "site_about")
    op.drop_column("users", "site_photos")
