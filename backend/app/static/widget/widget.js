(function () {
  var cfg = window.IaRadioWidget || {};
  var phone = cfg.phone || '';
  var business = cfg.business || 'Nosotros';
  var agent = cfg.agent || 'Asistente';
  var greeting = cfg.greeting || '¡Hola! ¿En qué puedo ayudarte?';
  var color = cfg.color || '#25D366';
  var position = cfg.position || 'right';

  // Inject CSS variable
  document.documentElement.style.setProperty('--iaradio-color', color);
  document.documentElement.style.setProperty('--iaradio-position', position);

  // Build popup
  var popup = document.createElement('div');
  popup.id = 'iaradio-widget-popup';
  popup.innerHTML = '<div id="iaradio-widget-header">' +
    '<div class="avatar">🎙️</div>' +
    '<div class="info"><div class="name">' + _esc(agent) + '</div>' +
    '<div class="sub">' + _esc(business) + ' • En línea</div></div></div>' +
    '<div id="iaradio-widget-body"><div class="iaradio-bubble">' + _esc(greeting) + '</div></div>' +
    '<div id="iaradio-widget-footer"><a href="https://wa.me/' + _clean(phone) +
    '" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" width="20" height="20" fill="#fff"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>Chatear por WhatsApp</a></div>';
  document.body.appendChild(popup);

  // Build button
  var btn = document.createElement('button');
  btn.id = 'iaradio-widget-btn';
  btn.setAttribute('aria-label', 'Abrir chat de WhatsApp');
  btn.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>';
  document.body.appendChild(btn);

  btn.addEventListener('click', function () {
    popup.classList.toggle('open');
  });

  document.addEventListener('click', function (e) {
    if (!popup.contains(e.target) && e.target !== btn) {
      popup.classList.remove('open');
    }
  });

  function _esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function _clean(p) { return p.replace(/\D/g, ''); }
})();
