(function () {
  var cfg = window.IaRadioWidget || {};
  var advertiserId = cfg.advertiserId || '';
  var apiBase = cfg.apiBase || 'https://www.iaradio.online/api/v1';
  var phone = cfg.phone || '';
  var business = cfg.business || 'Nosotros';
  var agent = cfg.agent || 'Asistente';
  var greeting = cfg.greeting || '¡Hola! ¿En qué puedo ayudarte?';
  var color = cfg.color || '#25D366';
  var position = cfg.position || 'right';
  var sessionId = null;
  var sending = false;

  // Inject CSS variable
  document.documentElement.style.setProperty('--iaradio-color', color);
  document.documentElement.style.setProperty('--iaradio-position', position);

  var waLinkHtml = phone
    ? '<a id="iaradio-widget-wa-link" href="https://wa.me/' + _clean(phone) + '" target="_blank" rel="noopener">' +
      '<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>' +
      'Continuar por WhatsApp</a>'
    : '';

  // Build popup
  var popup = document.createElement('div');
  popup.id = 'iaradio-widget-popup';
  popup.innerHTML = '<div id="iaradio-widget-header">' +
    '<div class="avatar">🎙️</div>' +
    '<div class="info"><div class="name">' + _esc(agent) + '</div>' +
    '<div class="sub">' + _esc(business) + ' • En línea</div></div></div>' +
    '<div id="iaradio-widget-body">' +
      '<div id="iaradio-widget-messages"><div class="iaradio-bubble iaradio-bubble-bot">' + _esc(greeting) + '</div></div>' +
    '</div>' +
    '<form id="iaradio-widget-input-row">' +
      '<input id="iaradio-widget-input" type="text" placeholder="Escribe tu pregunta..." autocomplete="off" />' +
      '<button id="iaradio-widget-send" type="submit" aria-label="Enviar">' +
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
      '</button>' +
    '</form>' +
    '<div id="iaradio-widget-lead">' +
      '<button id="iaradio-widget-lead-toggle" type="button">📋 Dejar mis datos para que me contacten</button>' +
      '<form id="iaradio-widget-lead-form" class="hidden">' +
        '<input id="iaradio-widget-lead-name" type="text" placeholder="Tu nombre" autocomplete="name" />' +
        '<input id="iaradio-widget-lead-phone" type="tel" placeholder="Tu teléfono (con código de país)" autocomplete="tel" />' +
        '<button type="submit">Enviar mis datos</button>' +
        '<p id="iaradio-widget-lead-error" class="hidden"></p>' +
      '</form>' +
    '</div>' +
    (waLinkHtml ? '<div id="iaradio-widget-footer">' + waLinkHtml + '</div>' : '');
  document.body.appendChild(popup);

  var messagesEl = popup.querySelector('#iaradio-widget-messages');
  var formEl = popup.querySelector('#iaradio-widget-input-row');
  var inputEl = popup.querySelector('#iaradio-widget-input');
  var leadWrap = popup.querySelector('#iaradio-widget-lead');
  var leadToggle = popup.querySelector('#iaradio-widget-lead-toggle');
  var leadForm = popup.querySelector('#iaradio-widget-lead-form');
  var leadNameEl = popup.querySelector('#iaradio-widget-lead-name');
  var leadPhoneEl = popup.querySelector('#iaradio-widget-lead-phone');
  var leadErrorEl = popup.querySelector('#iaradio-widget-lead-error');

  // Build button
  var btn = document.createElement('button');
  btn.id = 'iaradio-widget-btn';
  btn.setAttribute('aria-label', 'Abrir chat');
  btn.innerHTML = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.126.555 4.126 1.527 5.865L0 24l6.295-1.508A11.956 11.956 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 21.818a9.818 9.818 0 01-5.007-1.37l-.36-.213-3.735.894.944-3.646-.234-.374A9.818 9.818 0 012.182 12C2.182 6.57 6.57 2.182 12 2.182S21.818 6.57 21.818 12 17.43 21.818 12 21.818z"/></svg>';
  document.body.appendChild(btn);

  btn.addEventListener('click', function () {
    popup.classList.toggle('open');
    if (popup.classList.contains('open')) inputEl.focus();
  });

  document.addEventListener('click', function (e) {
    if (!popup.contains(e.target) && !btn.contains(e.target)) {
      popup.classList.remove('open');
    }
  });

  formEl.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = inputEl.value.trim();
    if (!text || sending || !advertiserId) return;
    _appendBubble(text, 'user');
    inputEl.value = '';
    _sendMessage(text);
  });

  leadToggle.addEventListener('click', function () {
    leadForm.classList.toggle('hidden');
  });

  leadForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var name = leadNameEl.value.trim();
    var phone = leadPhoneEl.value.trim();
    leadErrorEl.classList.add('hidden');
    if (!name || !phone) return;
    _sendLead(name, phone);
  });

  function _sendLead(name, phone) {
    var submitBtn = leadForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    fetch(apiBase + '/widget/lead/' + advertiserId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, phone: _formatPhone(phone), session_id: sessionId }),
    })
      .then(function (res) {
        if (!res.ok) return res.json().then(function (d) { throw new Error(d.detail || 'Error'); });
        return res.json();
      })
      .then(function (data) {
        sessionId = data.session_id || sessionId;
        leadWrap.innerHTML = '';
        _appendBubble('¡Gracias, ' + name + '! Un miembro del equipo te contactará pronto. 🙌', 'bot');
      })
      .catch(function (err) {
        leadErrorEl.textContent = err.message === 'Error' || !err.message
          ? 'No pudimos enviar tus datos. Intenta de nuevo.'
          : err.message;
        leadErrorEl.classList.remove('hidden');
        submitBtn.disabled = false;
      });
  }

  function _sendMessage(text) {
    sending = true;
    var typingEl = _appendBubble('…', 'bot', true);
    fetch(apiBase + '/widget/chat/' + advertiserId, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        sessionId = data.session_id || sessionId;
        typingEl.textContent = data.reply || 'Gracias por tu mensaje.';
        typingEl.classList.remove('iaradio-bubble-typing');
      })
      .catch(function () {
        typingEl.textContent = 'No pudimos enviar tu mensaje. Intenta de nuevo en un momento.';
        typingEl.classList.remove('iaradio-bubble-typing');
      })
      .finally(function () { sending = false; });
  }

  function _appendBubble(text, role, isTyping) {
    var b = document.createElement('div');
    b.className = 'iaradio-bubble iaradio-bubble-' + role + (isTyping ? ' iaradio-bubble-typing' : '');
    b.textContent = text;
    messagesEl.appendChild(b);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return b;
  }

  function _esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function _clean(p) { return p.replace(/\D/g, ''); }
  function _formatPhone(p) { return '+' + p.replace(/\D/g, ''); }
})();
