"""Fotos de la página del negocio vistas desde el servidor: la portada que
sale en la vista previa de WhatsApp. Mismo orden que el frontend
(PublicSitePage): fotos del dueño → su portada vieja → stock de su giro
(frontend/public/stock/{giro}/1.jpg, ver publicSite/utils.ts::stockGiro)."""
from app.models.user import User

STOCK_GIROS = {
    "restaurante", "tienda", "belleza", "gimnasio", "farmacia", "ferreteria", "panaderia",
    "corporativo", "inmobiliaria", "educacion", "automotriz", "tecnologia", "otro",
}
_KEYWORDS = [
    ("restaur", "restaurante"), ("comida", "restaurante"), ("taquer", "restaurante"),
    ("panader", "panaderia"), ("pastel", "panaderia"), ("cafe", "panaderia"), ("café", "panaderia"),
    ("estetic", "belleza"), ("salon", "belleza"), ("salón", "belleza"), ("barber", "belleza"), ("spa", "belleza"),
    ("fitness", "gimnasio"), ("deporte", "gimnasio"),
    ("salud", "farmacia"), ("clinic", "farmacia"), ("clínic", "farmacia"), ("dental", "farmacia"),
    ("ferreter", "ferreteria"), ("construc", "ferreteria"),
    ("ropa", "tienda"), ("boutique", "tienda"), ("moda", "tienda"),
    ("inmobil", "inmobiliaria"), ("bienes", "inmobiliaria"),
    ("escuela", "educacion"), ("academia", "educacion"), ("curso", "educacion"),
    ("taller", "automotriz"), ("auto", "automotriz"), ("mecánic", "automotriz"),
    ("software", "tecnologia"), ("tecnolog", "tecnologia"),
    ("consultor", "corporativo"), ("servicio", "corporativo"), ("empresa", "corporativo"),
]


def stock_giro(category: str | None) -> str:
    key = (category or "").lower().strip()
    if key in STOCK_GIROS:
        return key
    for word, giro in _KEYWORDS:
        if word in key:
            return giro
    return "otro"


def cover_photo_url(user: User, base_url: str) -> str:
    if user.site_photos:
        return user.site_photos[0]
    if user.hero_image_url:
        return user.hero_image_url
    return f"{base_url}/stock/{stock_giro(user.business_category)}/1.jpg"
