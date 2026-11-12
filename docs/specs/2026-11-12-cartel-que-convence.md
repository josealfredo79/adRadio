# Cartel de oferta que convence

Fecha: 2026-11-12 · Estado: construida

## Qué y para quién
Para el dueño del negocio: que la imagen de su promo antoje y se lea en el celular. Hoy el
«Cartel de colores» casi nunca trae el producto (solo si el Catálogo lo tiene con foto y con el
mismo nombre), parece volante de supermercado (rayas rojas y estrella amarilla, igual para todos
los negocios) y la mitad del texto no se lee a 300 px, que es como se ve en WhatsApp.

## Decisiones del dueño
- ¿Cómo se consigue la imagen del producto? → Pedírsela al dueño (botón de cámara) y guardarla en
  el Catálogo para la próxima. Nada de imágenes hechas con IA.
- ¿Qué va en el cartel? → Solo lo esencial: producto, precio grande, precio de antes, fecha y
  logo o nombre. Liga y "a domicilio" se quitan (ya van en el texto del mensaje). El teléfono
  sí va (cambio del 12-nov tras ver el cartel real).

## Casos (cada uno lleva su prueba)
1. Si el producto de la promo está en el Catálogo con foto, entonces el primer botón es «Foto de
   <producto>» y el cartel sale con esa foto en grande. — prueba: `TestCartelQueConvence::test_caso1_con_foto_en_el_catalogo_es_el_primer_boton` ✅
2. Si el producto no tiene foto (o no está en el Catálogo), entonces el Copiloto dice "Tómale una
   foto al <producto> y se ve mucho mejor" y el primer botón es «📷 Tomar foto» (en el celular abre
   la cámara o la galería). — prueba: `test_caso2_sin_foto_pide_tomarla_y_no_ofrece_fotos_de_otra_cosa` ✅ (+ frontend `shrinkPhoto.test.ts`: fotos de 6 MB se achican antes de subir)
3. Si el dueño sube la foto y el producto está en el Catálogo sin foto, entonces esa foto se le
   guarda al producto y la próxima promo de ese producto ya no la pide. — prueba: `test_caso3_la_foto_tomada_se_guarda_en_el_catalogo`, `test_caso3_no_cambia_la_foto_que_ya_tenia` ✅
4. Si el producto no está en el Catálogo, entonces la foto solo se usa en esa promo: no se crea
   un producto nuevo (el precio de la oferta no es su precio normal). — prueba: `test_caso4_si_no_esta_en_el_catalogo_no_se_crea` ✅
5. Si el dueño no quiere foto, entonces toca «Sin foto» y sale el cartel de solo letras, ya
   rediseñado (caso 7). Nunca se bloquea la promo por falta de foto. — prueba: `test_caso5_sin_foto_sale_el_cartel_de_letras` ✅
6. Con foto (del Catálogo o recién tomada), el cartel es el mismo diseño de oferta: la foto ocupa
   la mayor parte, el precio va en un sello grande, abajo el nombre del producto y la fecha.
   — prueba: `test_banner_quality.py::test_caso6_con_foto_la_foto_ocupa_el_cartel` ✅
7. Sin foto, el cartel lleva el precio enorme al centro, el producto arriba y la fecha abajo,
   con un fondo liso con degradado del color del giro del negocio, sin rayas ni puntitos.
   — prueba: `test_caso7_sin_foto_fondo_liso_sin_rayas` ✅
8. En el cartel no va ningún texto más chico que 44 px (en la imagen de 1080), para que se lea a
   300 px. El precio de antes tachado mide al menos 48 px. — prueba: `test_caso8_ningun_texto_mas_chico_que_44_px` ✅ (si "Antes $1,500" no cabe en el sello, sale solo "$1,500" tachado)
9. El cartel no lleva liga, "a domicilio" ni barra de "Escríbenos": eso va en el texto que
   acompaña la imagen. — prueba: `test_caso9_sin_domicilio_ni_barra_de_abajo` ✅
10. Si el negocio tiene logo, entonces sale arriba en un círculo; si no, el nombre del negocio en
    letras chicas pero legibles (44 px). — prueba: `test_caso10_logo_en_circulo_o_nombre` ✅
11. Si la foto que sube el dueño está oscura o es vertical, entonces se recorta al centro y no se
    deforma; si no se puede abrir, el Copiloto pide otra o sale «Sin foto». — prueba: `test_caso11_foto_vertical_se_recorta_y_una_rota_no_tumba_el_cartel`, `test_caso11_foto_de_otro_negocio_no_se_abre` ✅
12. Siguen las reglas de hoy: el precio y el "Antes" solo salen del texto del dueño o del
    Catálogo; la fecha concreta ("Solo hoy · jueves 12"); `$120`, no `$120.00`. — prueba: las de `test_banner_quality.py` y `test_campaign_builder.py` siguen verdes ✅

13. (Agregado 12-nov tras la prueba real: el dueño pidió el teléfono.) Arriba a la derecha va el
    teléfono en una cinta blanca: «WhatsApp 953 …» si el negocio tiene su número de Meta
    conectado; si no, «Tel. …» del teléfono de su perfil. Nunca el número personal de avisos
    (`whatsapp_number`), igual que el sitio público. Si el nombre del negocio no cabe al lado, se recorta o sale solo el
    teléfono. No hay campo de dirección en el perfil, así que la dirección no va.
    — prueba: `test_caso13_telefono_arriba_a_la_derecha`, `test_caso13_nombre_largo_no_se_encima_con_el_telefono`, `test_telefono_del_cartel` ✅
14. (Agregado 12-nov tras la prueba real.) Si el dueño nombra el producto corto ("cargador a $99")
    y en el Catálogo hay un solo producto que empieza así ("Cargador marca"), se usa ese (su foto y
    su "Antes"). Si dice algo que no está en ese nombre ("cargador samsung") o hay dos, ninguno.
    La foto tomada solo se guarda en el Catálogo con el nombre completo (podría ser de otro
    cargador).
    — prueba: `test_nombre_corto_encuentra_el_unico_producto` ✅

## Fuera de alcance
- Imágenes generadas con IA o quitar el fondo de la foto.
- Crear productos en el Catálogo desde la promo (caso 4).
- Varias fotos o carrusel en una promo.
- La cuña de audio y la promo de solo texto no cambian.
- El texto que acompaña la imagen no cambia (lo trabaja "Campañas que convencen", spec del 3-nov).

## Riesgos y costos
- Cambia la imagen de todas las promos nuevas de todos los negocios (no hay staging): se revisan
  carteles de muestra a 300 px antes de subir.
- No manda más mensajes ni cambia a quién se envía; Meta cobra lo mismo (una imagen por mensaje).
- Las fotos del dueño se guardan en el almacenamiento que ya se usa para el Catálogo (R2).
- Sin cambios a la base de datos.
- El cartel ahora es JPEG (~130–200 KB): con foto pesaba ~900 KB en PNG y tardaba 3–4 s en
  dibujarse; ahora ~0.4 s.
- Toca web y worker: se suben juntos (un push sube los tres servicios).

## Plan técnico
- `backend/app/services/banner_service.py`: nuevo `offer_banner_png` con dos diseños (con foto /
  sin foto), tamaños mínimos, sin barra de contacto; `photo_banner_png` deja de usarse para promos.
- `backend/app/domain/campaign_builder.py`: paso "photo" con botones «Foto de X» / «📷 Tomar foto»
  / «Sin foto»; toda foto pasa por el cartel de oferta; guardar la foto subida en el producto del
  Catálogo (solo si `_offer_product` lo encuentra sin duda y no tiene foto).
- `frontend/src/pages/campaigns/components/CampaignBuilderChat.tsx`: el botón «📷 Tomar foto» abre
  la cámara/galería (ya existe la subida a `/copilot/photo`).
- Pruebas: `backend/tests/test_campaign_builder.py`, `backend/tests/test_banner_quality.py`,
  `frontend/src/__tests__/CampaignBuilderChat.test.tsx`.

Tiempo estimado: ~1 día.

## Prueba real (la hace el dueño)
Desde el celular, en Campañas (o el Copiloto por WhatsApp), con CityCell:
1. Pide una promo de un producto del Catálogo que **tenga foto** → el primer botón debe decir
   «Foto de <producto>» y el cartel sale con esa foto, el precio en el círculo y la fecha abajo.
2. Pide una promo de un producto **sin foto** → debe pedirte «📷 Tomar foto»; tómala con la
   cámara. El cartel sale con tu foto. Luego abre el Catálogo: ese producto ya debe tener la foto.
3. Pide otra promo y toca «Sin foto» → precio enorme al centro, fondo liso de color.
4. Mándate la promo a ti mismo y mírala en el chat **sin abrirla**: precio, producto y fecha se
   deben leer.
