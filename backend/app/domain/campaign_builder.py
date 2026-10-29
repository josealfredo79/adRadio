"""La campaña que pregunta (spec docs/specs/2026-10-29-campana-que-pregunta.md).

El dueño arma una campaña de texto, foto o audio platicando: una pregunta a la
vez, con botones, y se salta lo que ya sabe. Es una sola pieza para todos los
canales: el panel web y WhatsApp la dibujan; por nota de voz sigue la promo
rápida de siempre.

El paso en que va se guarda en el borrador (`Campaign.ab_test["builder"]`),
así que si cierra a medias, al volver se retoma. Cada respuesta es:
    {campaign_id, step, text, choices: [{id, label, locked}], input,
     preview: {kind, text, image_url, audio_url} | None, done}
`input`: "what" (texto o voz), "edit" (cambiar el texto), "contact" (buscar
cliente), "photo" (subir foto) o None (solo botones).
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.campaign_actions import CampaignValidationError, validate_new_campaign
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.product import Product
from app.models.user import User

logger = logging.getLogger(__name__)

FORMATS = (("text", "Texto"), ("photo", "Con foto"), ("audio", "Audio de radio"))
# Los 7 estilos de cuña con nombres que entiende el dueño (campaign_mode → nombre).
STYLES = (
    ("radio", "Anuncio"), ("comunitaria", "Consejo"), ("capsula", "Dato curioso"), ("trivia", "Trivia"),
    ("historia", "Historia"), ("alerta", "Aviso"), ("estacional", "De temporada"),
)
_SCRIPT_MODE = {"radio": "classic"}  # generate_radio_script llama "classic" a la cuña de siempre
AUDIENCES = (("all", "Todos"), ("bought", "Los que compraron"), ("one", "Uno"))
DISCOUNTS = (10, 15, 20)
BOUGHT_DAYS = 90
RESUME_DAYS = 7

# Lo que el dueño dice y no hace falta preguntarle (respaldo por palabras).
_STYLE_WORDS = (
    ("capsula", r"dato curioso|sab[ií]as que|curiosidad"),
    ("trivia", r"trivia|adivina"),
    ("historia", r"historia|cuento|radionovela"),
    ("comunitaria", r"consejo|tip\b|recomendaci"),
    ("alerta", r"\baviso\b|alerta|lluvia|clima|calor|fr[ií]o"),
    ("estacional", r"temporada|navidad|muertos|d[ií]a de (las|los|la|el)|regreso a clases|fiestas patrias|buen fin"),
    ("radio", r"\bcu[ñn]a\b|\banuncio\b"),
)
_AUDIO_WORDS = r"\baudio\b|\bcu[ñn]a\b|\bradio\b|locutor|nota de voz|\bspot\b"
_PHOTO_WORDS = r"\bfoto\b|\bimagen\b|\bcartel\b|\bbanner\b|\bflyer\b"
_TEXT_WORDS = r"\b(solo )?texto\b|\bmensaje escrito\b"
_BOUGHT_WORDS = r"(los|a los|clientes) que (me |ya |te )?compraron|compradores"
_ALL_WORDS = r"\ba todos\b|todos mis clientes|todos los clientes"
_PERCENT = re.compile(r"(?<!\d)(\d{1,3})\s?(%|por\s*ciento)")


def guess(what: str) -> dict:
    """Lo que se puede saber de lo que dijo el dueño: formato, estilo, a quién.
    Solo lo que nombró (explícito); el resto se pregunta."""
    low = what.lower()
    out: dict = {}
    style = next((mode for mode, pat in _STYLE_WORDS if re.search(pat, low)), None)
    if re.search(_AUDIO_WORDS, low):
        out["format"] = "audio"
    elif re.search(_PHOTO_WORDS, low):
        out["format"] = "photo"
    elif re.search(_TEXT_WORDS, low):
        out["format"] = "text"
    if style and out.get("format") in (None, "audio") and style != "radio":
        out["suggest_style"] = style
        if out.get("format") == "audio":
            out["style"] = style
    elif style == "radio" and out.get("format") == "audio":
        out["style"] = "radio"
    if re.search(_BOUGHT_WORDS, low):
        out["audience"] = "bought"
    elif re.search(_ALL_WORDS, low):
        out["audience"] = "all"
    return out


def keep_said(args: dict, owner_texts: list[str]) -> dict:
    """Del Copiloto solo se queda lo que el dueño dijo: con la IA real (Gemini)
    "haz una campaña de 2x1" llegaba con format="text" y se saltaba la
    pregunta "¿Cómo se lo mando?". Igual que keep_asked_discount."""
    said = " ".join(owner_texts)
    g = guess(said)
    out = {"what": args.get("what") or said}
    for key in ("format", "style", "audience"):
        if args.get(key) and g.get(key) == args[key]:
            out[key] = args[key]
    if args.get("audience") == "one" and args.get("contact") and args["contact"].lower() in said.lower():
        out.update(audience="one", contact=args["contact"])
    return out


def promised_percent(text: str) -> int | None:
    m = _PERCENT.search(text or "")
    return int(m.group(1)) if m else None


def _label(pairs, key) -> str:
    return dict(pairs).get(key, key)


def _choice(cid: str, label: str, locked: bool = False) -> dict:
    return {"id": cid, "label": f"🔒 {label}" if locked else label, "locked": locked}


def _state(camp: Campaign) -> dict:
    return dict((camp.ab_test or {}).get("builder") or {})


def _save(camp: Campaign, state: dict, **ab) -> None:
    # Reasignar el dict entero: SQLAlchemy no ve cambios dentro del JSON.
    camp.ab_test = {**(camp.ab_test or {}), **ab, "builder": state}


def _reply(camp: Campaign | None, step: str, text: str, choices=(), input_=None, preview=None, done=False) -> dict:
    return {
        "campaign_id": str(camp.id) if camp else None, "step": step, "text": text,
        "choices": list(choices), "input": input_, "preview": preview, "done": done,
    }


# ── Contenido ──────────────────────────────────────────────────────────────────

async def _variants(db: AsyncSession, user: User, what: str) -> list[str]:
    from app.services.claude_service import generate_campaign_variants
    from app.services.rag_service import catalog_context

    try:
        out = await generate_campaign_variants(
            campaign_type="promo", business_name=user.business_name or "", intent=what,
            catalog=await catalog_context(db, str(user.id)),
        )
    except Exception:
        logger.warning("[BUILDER] text generation failed user=%s", user.id, exc_info=True)
        out = []
    return [v.strip() for v in out if v and v.strip()]


async def _make_text(db, user, camp, state, fresh: bool = False) -> str | None:
    if fresh or not state.get("variants"):
        state["variants"] = await _variants(db, user, state["what"])
        state["vi"] = 0
    if not state["variants"]:
        return "No pude armar el mensaje ahorita. Toca «Otra versión» o escríbelo tú con «Cambiar el texto»."
    camp.message_text = state["variants"][state["vi"] % len(state["variants"])]
    return None


async def _make_audio(user, camp, state, script: str | None = None) -> str | None:
    from app.services.radio.scripts import radio_business
    from app.services.radio_service import generate_radio_ad, generate_radio_script

    style = state["style"]
    mode = _SCRIPT_MODE.get(style, style)
    business_name, contact = radio_business(user)
    try:
        if not script:
            script = await generate_radio_script(
                business_name=business_name, message_or_intent=state["what"], mode=mode,
                business_category=user.business_category, contact=contact,
            )
        audio_url = await generate_radio_ad(
            business_name=business_name, message_or_intent=state["what"], _script=script, mode=mode,
            business_category=user.business_category,
        )
    except Exception:
        logger.warning("[BUILDER] audio generation failed user=%s", user.id, exc_info=True)
        audio_url = None
    if not audio_url:
        return "No pude grabar la cuña ahorita. Toca «Otra versión» para intentar de nuevo."
    camp.message_text = camp.name  # el aviso dice "🔊 Toca para escucharla. <esto>"
    _save(camp, state, campaign_mode=style, audio_url=audio_url, radio_script=script)
    return None


def _price(product: Product | None) -> str:
    if not product or product.price is None:
        return ""
    n = float(product.price)
    return f"${n:,.0f}" if n.is_integer() else f"${n:,.2f}"


def _own_file(url: str | None) -> bool:
    """Solo se abren fotos guardadas por IaRadio (upload_bytes o R2 propio):
    nunca una dirección cualquiera que llegue del navegador (SSRF)."""
    from app.config import settings

    if not url:
        return False
    if url.startswith(f"{settings.BASE_URL}/api/v1/radio/audio/"):
        return ".." not in url
    public = (settings.CF_R2_PUBLIC_URL or "").rstrip("/")
    return bool(public) and url.startswith(f"{public}/")


async def _make_photo(db, user, camp, state) -> str | None:
    from app.services.banner_service import (
        generate_banner_copy_with_claude,
        generate_banner_png,
        photo_banner_png,
        select_design,
    )
    from app.services.storage_service import read_bytes, upload_bytes

    error = await _make_text(db, user, camp, state)
    if error:
        return error
    source = state.get("photo") or "poster"
    try:
        if source == "poster":
            design = select_design(user.business_category, "promo")
            copy = await generate_banner_copy_with_claude(
                business_name=user.business_name or "", contact_name="", promo_description=state["what"],
                business_category=user.business_category,
            )
            png, ext, ctype = generate_banner_png(copy, design.palette, design.layout), "png", "image/png"
        else:
            product = None
            url = source
            if source.startswith("p:"):
                product = await db.get(Product, uuid.UUID(source[2:]))
                url = product.photo_url if product and product.advertiser_id == user.id else ""
            raw = await read_bytes(url) if _own_file(url) else None
            if not raw:
                return "No pude abrir esa foto. Escoge otra o toca «Cartel de colores»."
            png = photo_banner_png(raw, camp.name, _price(product), user.business_name or "")
            ext, ctype = "jpg", "image/jpeg"
        image_url = await upload_bytes(png, f"campaign_banners/{user.id}/{uuid.uuid4()}.{ext}", ctype)
    except Exception:
        logger.warning("[BUILDER] photo failed user=%s", user.id, exc_info=True)
        image_url = None
    if not image_url:
        return "No pude armar la imagen ahorita. Toca «Otra versión» o «Cartel de colores»."
    camp.image_url = image_url
    # photo_fixed: se manda esta misma imagen a todos (no una por cliente).
    _save(camp, state, campaign_mode="banner", photo_fixed=True, banner_caption=camp.message_text)
    return None


async def _make_content(db, user, camp, state, fresh: bool = False) -> str | None:
    fmt = state["format"]
    if fmt == "audio":
        return await _make_audio(user, camp, state)
    if fmt == "photo":
        if fresh and state.get("variants"):
            state["vi"] = state.get("vi", 0) + 1
        return await _make_photo(db, user, camp, state)
    if fresh and state.get("variants"):
        state["vi"] = state.get("vi", 0) + 1
        if state["vi"] >= len(state["variants"]):
            return await _make_text(db, user, camp, state, fresh=True)
    error = await _make_text(db, user, camp, state)
    if not error:
        _save(camp, state, campaign_mode="regular")
    return error


def _preview(camp: Campaign, state: dict) -> dict:
    ab = camp.ab_test or {}
    fmt = state.get("format")
    if fmt == "audio":
        return {"kind": "audio", "text": ab.get("radio_script") or "", "image_url": None, "audio_url": ab.get("audio_url")}
    if fmt == "photo":
        return {"kind": "image", "text": camp.message_text, "image_url": camp.image_url, "audio_url": None}
    return {"kind": "text", "text": camp.message_text, "image_url": None, "audio_url": None}


# ── Preguntas ──────────────────────────────────────────────────────────────────

async def _locked(db, user, camp, fmt: str) -> str | None:
    from app.services.campaign_quota import quota_block

    kind = {"audio": "audio", "photo": "image"}.get(fmt)
    return await quota_block(db, user, kind, exclude=camp.id if camp else None)


async def _ask(db: AsyncSession, user: User, camp: Campaign, note: str = "") -> dict:
    state = _state(camp)
    step = state.get("step")
    lead = f"{note}\n\n" if note else ""

    if step == "format":
        order = [state["suggest"]] + [f for f, _ in FORMATS if f != state["suggest"]]
        choices = [_choice(f"f:{f}", _label(FORMATS, f), bool(await _locked(db, user, camp, f))) for f in order]
        return _reply(camp, step, f"{lead}¿Cómo se lo mando?", choices)

    if step == "style":
        sug = state.get("suggest_style") or "radio"
        order = [sug] + [m for m, _ in STYLES if m != sug]
        return _reply(camp, step, f"{lead}¿De qué estilo la cuña?", [_choice(f"s:{m}", _label(STYLES, m)) for m in order])

    if step == "photo":
        products = await _photo_products(db, user, state["what"])
        choices = [_choice(f"p:{p.id}", f"Foto de {p.name}"[:40]) for p in products]
        choices += [_choice("upload", "Subir una foto"), _choice("poster", "Cartel de colores")]
        return _reply(camp, step, f"{lead}¿Con qué foto?", choices, input_="photo")

    if step == "preview":
        kind = state["format"]
        ask = {"audio": "Escúchala. ¿Así está bien?", "photo": "Así la ve tu cliente. ¿Así está bien?"}.get(
            kind, "Así le llega a tu cliente. ¿Así está bien?")
        choices = [_choice("ok", "Así está bien"), _choice("other", "Otra versión"), _choice("edit", "Cambiar el texto")]
        return _reply(camp, step, f"{lead}{ask}", choices, preview=_preview(camp, state))

    if step == "edit":
        return _reply(camp, step, f"{lead}Escribe cómo quieres que diga:", input_="edit")

    if step == "audience":
        return _reply(camp, step, f"{lead}¿A quién se la mando?", [_choice(f"a:{a}", lbl) for a, lbl in AUDIENCES])

    if step == "contact":
        hits = state.get("hits") or []
        choices = [_choice(f"c:{h['id']}", f"{h['name']} (…{h['phone'][-4:]})") for h in hits]
        text = "¿Cuál de ellos?" if hits else "¿A qué cliente? Escribe su nombre o teléfono."
        return _reply(camp, step, f"{lead}{text}", choices, input_="contact")

    if step == "discount":
        pct = state.get("promised")
        if pct in DISCOUNTS:
            return _reply(camp, step, f"{lead}Tu mensaje dice {pct}%. ¿Le pongo un cupón de {pct}% a cada cliente?",
                          [_choice(f"d:{pct}", "Sí"), _choice("d:0", "No")])
        return _reply(camp, step, f"{lead}¿Le pones cupón de descuento?",
                      [_choice(f"d:{d}", f"{d}%") for d in DISCOUNTS] + [_choice("d:0", "No")])

    if step == "send":
        return await _ask_send(db, user, camp, lead)

    return _reply(camp, "what", f"{lead}¿Qué quieres anunciar?", input_="what")


async def _ask_send(db, user, camp, lead: str) -> dict:
    from app.services.campaign_reach import campaign_reach, whatsapp_connected
    from app.services.copilot_promo_tools import _pesos, reach_line
    from app.services.messaging_throttle import send_starts_label

    reach = await campaign_reach(db, camp)
    if reach["web"] + reach["web_chat"] == 0 and not (reach["whatsapp_connected"] and reach["whatsapp"]):
        state = _state(camp)
        state["step"] = "audience"
        _save(camp, state)
        await db.commit()
        why = (f"Nadie te ha comprado en los últimos {BOUGHT_DAYS} días (con «Cobré» o pedido)."
               if (camp.segment or {}).get("bought_days") else "Todavía no tienes clientes a quién mandarla.")
        return await _ask(db, user, camp, why)
    text = f"{lead}Le llega: {reach_line(reach, web_only=True)}."
    later = send_starts_label()
    if later:
        text += f"\nEs de noche: sale {later}"
    choices = [_choice("web", "Mandar gratis por web")]
    if whatsapp_connected(user) and reach["whatsapp"] > 0:
        choices.append(_choice("whatsapp", f"También por WhatsApp (aprox {_pesos(reach['whatsapp_cost_mxn'])})"))
    return _reply(camp, "send", text, choices)


async def _photo_products(db, user, what: str, limit: int = 3) -> list[Product]:
    rows = (await db.execute(
        select(Product).where(Product.advertiser_id == user.id, Product.active.is_(True),
                              Product.photo_url.is_not(None), Product.photo_url != "")
    )).scalars().all()
    words = {w for w in re.findall(r"\w{3,}", what.lower())}

    def score(p: Product) -> int:
        name = p.name.lower()
        # "micas" ~ "mica": basta con que la palabra empiece igual (4 letras).
        return sum(1 for w in words if w[:4] in name)

    return [p for p in sorted(rows, key=score, reverse=True) if score(p) > 0][:limit] or rows[:limit]


# ── Avanzar ────────────────────────────────────────────────────────────────────

async def _after_content(db, user, camp, state) -> None:
    """Qué sigue tras la vista previa aprobada."""
    if state.get("audience"):
        await _set_audience(db, user, camp, state, state["audience"], state.get("contact"))
    else:
        state["step"] = "audience"


async def _set_audience(db, user, camp, state, audience: str, who: str | None = None) -> None:
    state["audience"] = audience
    if audience == "bought":
        camp.segment = {"bought_days": BOUGHT_DAYS}
    elif audience == "one":
        camp.segment = {"specific_contacts": []}
        state["step"] = "contact"
        if who:
            await _search(db, user, state, who)
        return
    else:
        camp.segment = {}
    _to_discount_or_send(camp, state)


def _to_discount_or_send(camp, state) -> None:
    pct = promised_percent(f"{state.get('what', '')} {camp.message_text or ''}")
    wants = pct or re.search(r"descuento|cup[oó]n", state.get("what", "").lower())
    if wants and not state.get("discount_asked"):
        state["promised"] = pct
        state["step"] = "discount"
    else:
        state["step"] = "send"


async def _search(db, user, state, who: str) -> None:
    like = f"%{who.strip()}%"
    rows = (await db.execute(
        select(Contact).where(Contact.advertiser_id == user.id, Contact.status == "active",
                              or_(Contact.name.ilike(like), Contact.phone.ilike(like)))
        .order_by(Contact.name).limit(5)
    )).scalars().all()
    state["hits"] = [{"id": str(c.id), "name": c.name, "phone": c.phone or ""} for c in rows]


async def _goto_content(db, user, camp, state) -> str | None:
    """Del formato (y estilo/foto) a la vista previa: genera el contenido."""
    fmt = state["format"]
    if fmt == "audio" and not state.get("style"):
        state["step"] = "style"
        return None
    if fmt == "photo" and not state.get("photo"):
        state["step"] = "photo"
        return None
    error = await _make_content(db, user, camp, state)
    state["step"] = "preview"
    if error and fmt == "photo":  # esa foto no sirvió: que escoja otra
        state.pop("photo", None)
        state["step"] = "photo"
    return error


async def _new(db: AsyncSession, user: User, what: str, prefill: dict | None = None) -> tuple[Campaign | None, str]:
    from app.services.copilot_promo_tools import campaign_name

    what = " ".join(what.split())
    try:
        validate_new_campaign(user, name=campaign_name(what), message_text=what, type_="promo",
                              status="draft", segment={})
    except CampaignValidationError as e:
        return None, e.detail
    guessed = {**guess(what), **{k: v for k, v in (prefill or {}).items() if v}}
    products = await _photo_products(db, user, what, limit=1)
    suggest = guessed.get("format") or ("audio" if guessed.get("suggest_style") else "photo" if products else "text")
    state = {"what": what, "suggest": suggest, "step": "format",
             **{k: guessed[k] for k in ("format", "style", "suggest_style", "audience", "contact") if k in guessed}}
    camp = Campaign(advertiser_id=user.id, name=campaign_name(what), type="promo", message_text=what,
                    segment={}, status="draft", ab_test={"enabled": False, "campaign_mode": "regular", "web_only": True})
    db.add(camp)
    await db.flush()
    note = ""
    if state.get("format"):
        why = await _locked(db, user, camp, state["format"])
        if why:
            state.pop("format")
            note = why
        else:
            note = await _goto_content(db, user, camp, state) or ""
    _save(camp, state)
    await db.commit()
    return camp, note


async def _pending_draft(db: AsyncSession, user: User) -> Campaign | None:
    since = datetime.now(timezone.utc) - timedelta(days=RESUME_DAYS)
    rows = (await db.execute(
        select(Campaign).where(Campaign.advertiser_id == user.id, Campaign.status == "draft",
                               Campaign.created_at >= since)
        .order_by(Campaign.created_at.desc()).limit(10)
    )).scalars().all()
    return next((c for c in rows if _state(c).get("step") not in (None, "done")), None)


async def handle(db: AsyncSession, user: User, campaign_id: str | None = None, choice: str | None = None,
                 text: str | None = None, prefill: dict | None = None) -> dict:
    """Una vuelta de la plática: empezar, retomar o contestar."""
    text = (text or "").strip()

    if not campaign_id:
        if choice and choice.startswith("resume:"):
            camp = await _owned(db, user, choice[7:])
            return await _ask(db, user, camp) if camp else await handle(db, user)
        if text or (prefill and prefill.get("what")):
            camp, note = await _new(db, user, text or prefill["what"], prefill)
            if not camp:
                return _reply(None, "what", note, input_="what")
            return await _ask(db, user, camp, note)
        if choice != "new":
            pending = await _pending_draft(db, user)
            if pending:
                return _reply(pending, "resume", f"¿Seguimos con tu promo «{pending.name}»?",
                              [_choice(f"resume:{pending.id}", "Seguir"), _choice("new", "Empezar otra")])
        return _reply(None, "what", "¿Qué quieres anunciar?", input_="what")

    camp = await _owned(db, user, campaign_id)
    if not camp:
        return _reply(None, "what", "Esa campaña ya no existe. ¿Qué quieres anunciar?", input_="what")
    if camp.status != "draft":
        return _reply(camp, "done", "Esta promo ya se mandó.", done=True)
    state = _state(camp)
    step = state.get("step")
    note = ""

    if step == "format" and choice and choice[2:] in dict(FORMATS) and choice.startswith("f:"):
        fmt = choice[2:]
        why = await _locked(db, user, camp, fmt)
        if why:
            return await _ask(db, user, camp, why)
        state["format"] = fmt
        note = await _goto_content(db, user, camp, state) or ""
    elif step == "style" and choice and choice.startswith("s:") and choice[2:] in dict(STYLES):
        state["style"] = choice[2:]
        note = await _goto_content(db, user, camp, state) or ""
    elif step == "photo" and (choice in ("poster",) or (choice or "").startswith("p:") or (choice == "upload" and text)):
        state["photo"] = text if choice == "upload" else choice
        note = await _goto_content(db, user, camp, state) or ""
    elif step == "preview" and choice == "ok":
        await _after_content(db, user, camp, state)
    elif step == "preview" and choice == "other":
        note = await _make_content(db, user, camp, state, fresh=True) or ""
    elif step == "preview" and choice == "edit":
        state["step"] = "edit"
    elif step == "edit" and text:
        state["step"] = "preview"
        if state["format"] == "audio":
            note = await _make_audio(user, camp, state, script=text) or ""
        else:
            state["variants"] = [text] + [v for v in state.get("variants", []) if v != text]
            state["vi"] = 0
            note = await _make_content(db, user, camp, state) or ""
    elif step == "audience" and choice and choice.startswith("a:"):
        await _set_audience(db, user, camp, state, choice[2:])
    elif step == "contact" and choice and choice.startswith("c:"):
        hit = next((h for h in state.get("hits", []) if h["id"] == choice[2:]), None)
        if hit:
            camp.segment = {"specific_contacts": [hit["id"]]}
            state["who"] = hit["name"]
            _to_discount_or_send(camp, state)
    elif step == "contact" and text:
        await _search(db, user, state, text)
        if not state["hits"]:
            note = f"No encontré a «{text}» entre tus clientes."
    elif step == "discount" and choice in {f"d:{d}" for d in (0, *DISCOUNTS)}:
        pct = int(choice[2:])
        state["discount_asked"] = True
        ab = {k: v for k, v in (camp.ab_test or {}).items()
              if k not in ("has_coupon", "coupon_description", "coupon_percent", "coupon_hours")}
        if pct:
            ab.update(has_coupon=True, coupon_description=f"{pct}% de descuento", coupon_percent=pct, coupon_hours=72)
        camp.ab_test = ab
        state["step"] = "send"
    elif step == "send" and choice in ("web", "whatsapp"):
        return await _send(db, user, camp, state, web_only=choice == "web")

    _save(camp, state)
    await db.commit()
    return await _ask(db, user, camp, note)


async def _send(db, user, camp, state, web_only: bool) -> dict:
    from app.services.campaign_reach import whatsapp_connected
    from app.services.copilot_promo_tools import start_campaign
    from app.services.messaging_throttle import send_starts_label

    if not web_only and not whatsapp_connected(user):
        web_only = True
    # Candado: si "Mandar" llega dos veces (dos pestañas, reintento de red), la
    # segunda espera aquí y ve que ya salió; si no, saldría doble (y Meta cobra
    # doble). revisor-dinero, 2026-10-29.
    camp = (await db.execute(
        select(Campaign).where(Campaign.id == camp.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if camp.status != "draft":
        return _reply(camp, "done", "Esta promo ya se mandó.", done=True)
    state = _state(camp)
    state["step"] = "done"
    _save(camp, state)
    error = await start_campaign(db, user, camp, web_only, source="builder")
    if error:
        await db.rollback()
        camp = await db.get(Campaign, camp.id)
        return await _ask(db, user, camp, error)
    how = "gratis por web" if web_only else "por web y WhatsApp"
    later = send_starts_label()
    text = f"¡Listo! Tu promo va {how}." + (f" Sale {later}" if later else "")
    return _reply(camp, "done", text, done=True)


async def _owned(db, user, campaign_id: str) -> Campaign | None:
    try:
        camp = await db.get(Campaign, uuid.UUID(str(campaign_id)))
    except (ValueError, TypeError):
        return None
    return camp if camp and camp.advertiser_id == user.id else None
