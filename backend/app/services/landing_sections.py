"""Canonical ordered section ids for the public landing page (/sitio/{slug}) —
shared by ProfileUpdate's validator (schemas/profile.py) and the public site
endpoint's default (api/v1/public_site.py) so both agree on the same set/order
without importing an API router from a schema module."""

LANDING_SECTION_IDS = ["beneficios", "opiniones", "catalogo", "nosotros_horario"]

# Default when landing_sections is null: current hardcoded order, all visible.
DEFAULT_LANDING_SECTIONS = list(LANDING_SECTION_IDS)
