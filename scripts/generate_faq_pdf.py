#!/usr/bin/env python3
"""Generate FAQ IaRadio PDF with Unicode font support."""
from fpdf import FPDF
import os

FONT_DIR = "/usr/share/fonts/truetype/dejavu"

class IaRadioPDF(FPDF):
    def setup_fonts(self):
        self.add_font("DejaVu", "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
        # No italic available, use regular as fallback
        self.add_font("DejaVu", "I", os.path.join(FONT_DIR, "DejaVuSans.ttf"))

    def header(self):
        self.set_font("DejaVu", "B", 10)
        self.set_text_color(103, 76, 196)
        self.cell(0, 8, "IaRadio - Preguntas Frecuentes", align="R")
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"www.iaradio.online  |  Pagina {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(103, 76, 196)
        self.cell(0, 10, title)
        self.ln(8)
        self.set_draw_color(103, 76, 196)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def body_text(self, text):
        self.set_font("DejaVu", "", 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font("DejaVu", "", 11)
        self.set_text_color(40, 40, 40)
        self.cell(8, 6, "-")
        self.multi_cell(0, 6, text)
        self.ln(1)

    def bold_text(self, label, text):
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(40, 40, 40)
        self.cell(self.get_string_width(label) + 2, 6, label)
        self.set_font("DejaVu", "", 11)
        self.multi_cell(0, 6, text)
        self.ln(1)


pdf = IaRadioPDF()
pdf.setup_fonts()
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# Cover
pdf.set_font("DejaVu", "B", 28)
pdf.set_text_color(103, 76, 196)
pdf.ln(40)
pdf.cell(0, 15, "IaRadio", align="C")
pdf.ln(18)
pdf.set_font("DejaVu", "", 16)
pdf.set_text_color(80, 80, 80)
pdf.cell(0, 10, "Preguntas Frecuentes", align="C")
pdf.ln(12)
pdf.set_font("DejaVu", "", 12)
pdf.cell(0, 8, "Plataforma de marketing digital con IA para negocios", align="C")
pdf.ln(30)

# URL
pdf.set_font("DejaVu", "", 11)
pdf.set_text_color(103, 76, 196)
pdf.cell(0, 8, "www.iaradio.online", align="C")
pdf.ln(5)
pdf.set_text_color(120, 120, 120)
pdf.set_font("DejaVu", "I", 10)
pdf.cell(0, 8, "Contacto: soporte@iaradio.online", align="C")

# Page 2 - FAQ
pdf.add_page()

pdf.section_title("Que es IaRadio?")
pdf.body_text(
    "IaRadio es una plataforma SaaS que transforma el WhatsApp de los negocios "
    "en una maquina de ventas y retencion de clientes. A diferencia de los chatbots "
    "tradicionales (menus de botones aburridos), IaRadio usa Inteligencia Artificial "
    "avanzada para mantener conversaciones naturales y vender como un humano."
)

pdf.section_title("Que tecnologias usa?")
pdf.bullet("Claude AI (Anthropic): El cerebro. Conversaciones naturales, entiende contexto.")
pdf.bullet("Whisper (OpenAI): El oido. Transcribe notas de voz de WhatsApp.")
pdf.bullet("Voyage AI (RAG): La memoria. Lee PDF, catalogos y menus del negocio.")
pdf.bullet("Fish Audio: La voz. Genera cunas de radio de calidad profesional.")

pdf.section_title("Como ayuda a mi negocio?")
pdf.bold_text("Clinicas y dentistas: ", "Reduce citas canceladas con recordatorios automaticos. Agenda citas via WhatsApp.")
pdf.bold_text("Restaurantes: ", "Envia el menu del dia como programa de radio. Aumenta reservaciones.")
pdf.bold_text("Inmobiliarias: ", "Atiende prospectos 24/7 con notas de voz automaticas. Califica clientes.")
pdf.bold_text("Tiendas: ", "Campanas masivas de promociones. Cupones con QR para medir canjes.")

pdf.section_title("Funcionalidades principales")
pdf.bullet("Campanas masivas por WhatsApp sin riesgo de baneo.")
pdf.bullet("Bot IA que responde clientes con informacion real de tu negocio.")
pdf.bullet("Cunas de radio generadas con IA en segundos.")
pdf.bullet("Cupones automaticos con seguimiento de canjes.")
pdf.bullet("Panel de control en tiempo real con analytics.")
pdf.bullet("Integracion con Google Calendar para citas.")

# Page 3 - Planes
pdf.add_page()
pdf.section_title("Planes y Precios")

pdf.set_font("DejaVu", "B", 12)
pdf.set_text_color(103, 76, 196)
pdf.cell(0, 8, "Plan Starter - $499/mes")
pdf.ln(7)
pdf.set_font("DejaVu", "", 11)
pdf.set_text_color(40, 40, 40)
pdf.bullet("500 mensajes al mes")
pdf.bullet("Bot de WhatsApp basico")
pdf.bullet("Campanas publicitarias")
pdf.bullet("Importacion de contactos por CSV")
pdf.bullet("Base de conocimiento (sube PDF, DOCX, TXT)")
pdf.ln(4)

pdf.set_font("DejaVu", "B", 12)
pdf.set_text_color(103, 76, 196)
pdf.cell(0, 8, "Plan Growth - $999/mes")
pdf.ln(7)
pdf.set_font("DejaVu", "", 11)
pdf.set_text_color(40, 40, 40)
pdf.bullet("1,000 mensajes al mes")
pdf.bullet("Todo lo de Starter")
pdf.bullet("Bot con RAG (inteligencia con base de conocimiento)")
pdf.bullet("3 cunas de radio al mes")
pdf.bullet("Cupones con QR")
pdf.ln(4)

pdf.set_font("DejaVu", "B", 12)
pdf.set_text_color(103, 76, 196)
pdf.cell(0, 8, "Plan Pro - $2,499/mes")
pdf.ln(7)
pdf.set_font("DejaVu", "", 11)
pdf.set_text_color(40, 40, 40)
pdf.bullet("3,000 mensajes al mes")
pdf.bullet("Todo lo de Growth")
pdf.bullet("Cunas de radio ilimitadas")
pdf.bullet("Numero de WhatsApp dedicado")
pdf.bullet("URLs personalizadas para cupones")
pdf.bullet("Automatizaciones ilimitadas")
pdf.ln(4)

pdf.set_font("DejaVu", "B", 12)
pdf.set_text_color(103, 76, 196)
pdf.cell(0, 8, "Plan Business - $6,799/mes")
pdf.ln(7)
pdf.set_font("DejaVu", "", 11)
pdf.set_text_color(40, 40, 40)
pdf.bullet("10,000 mensajes al mes")
pdf.bullet("Todo lo de Pro")
pdf.bullet("Integraciones avanzadas")
pdf.bullet("Soporte dedicado 24/7")
pdf.bullet("Acceso completo a todas las IA")

pdf.ln(8)
pdf.set_font("DejaVu", "I", 10)
pdf.set_text_color(100, 100, 100)
pdf.cell(0, 8, "Todos los planes incluyen 15 dias de prueba gratis. Sin contratos forzosos.", align="C")

# Page 4 - Como funciona
pdf.add_page()
pdf.section_title("Como funciona? (Paso a paso)")
pdf.body_text("1. Te registras gratis en www.iaradio.online/register")
pdf.body_text("2. Subes la informacion de tu negocio (PDF, menu, catalogo)")
pdf.body_text("3. Configuras tu bot de WhatsApp en 10 minutos")
pdf.body_text("4. El bot empieza a responder clientes automaticamente")
pdf.body_text("5. Creas campanas masivas para enviar promociones")
pdf.body_text("6. Ves los resultados en tu panel de control en tiempo real")

pdf.ln(4)
pdf.section_title("Tecnologia anti-ban")
pdf.body_text(
    "IaRadio usa un sistema inteligente de distribucion de mensajes que evita "
    "que tu numero sea bloqueado por WhatsApp. Los mensajes se envian desde "
    "multiples numeros del pool, con intervalos naturales y contenido variado."
)

pdf.section_title("Soporte")
pdf.body_text("Email: soporte@iaradio.online")
pdf.body_text("WhatsApp: +52 56 71 25 40 39")
pdf.body_text("Horario: Lunes a viernes 9:00 - 18:00 (hora CDMX)")

out = os.path.join(os.path.dirname(__file__), "..", "faq_iaradio.pdf")
pdf.output(out)
print(f"Saved {out}")
