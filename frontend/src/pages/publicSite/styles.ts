export const PUBLIC_SITE_STYLES = `
html {
  scroll-behavior: smooth;
}
.psite-anchor {
  scroll-margin-top: 84px;
}
.psite-nav-link {
  opacity: .7;
  transition: opacity .15s ease;
}
@media (hover: hover) and (pointer: fine) {
  .psite-nav-link:hover {
    opacity: 1;
  }
}
.psite-nav-links {
  display: none;
  align-items: center;
  gap: 24px;
}
.psite-nav-cta {
  display: none;
}
@media (min-width: 640px) {
  /* the embedded WhatsApp widget ships its own global ".hidden { display: none !important }"
     rule with no scoping, which clobbers Tailwind's "hidden sm:*" pattern on this page —
     these two classes exist to sidestep that collision by never being named "hidden". */
  .psite-nav-links {
    display: flex;
  }
  .psite-nav-cta {
    display: inline-flex;
  }
}
.psite-mobile-link {
  transition: background-color .15s ease;
}
.psite-mobile-link:active {
  background-color: rgba(127,127,127,.1);
}
@keyframes psiteFadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.psite-hover-lift {
  transition: transform 200ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 200ms ease;
}
.psite-btn-primary {
  transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 200ms ease;
}
/* Hover solo con mouse: en el celular se quedaba "pegado" tras tocar. */
@media (hover: hover) and (pointer: fine) {
  .psite-hover-lift:hover {
    transform: translateY(-4px);
    box-shadow: 0 16px 32px -12px var(--psite-glow, rgba(0,0,0,.35));
  }
  .psite-btn-primary:hover {
    transform: scale(1.02);
    box-shadow: 0 12px 28px -8px var(--psite-glow, rgba(0,0,0,.35));
  }
}
.psite-btn-primary:active {
  transform: scale(.97);
}
@media (prefers-reduced-motion: reduce) {
  .psite-hover-lift, .psite-btn-primary { transition: box-shadow 200ms ease; }
  .psite-hover-lift:hover, .psite-btn-primary:hover, .psite-btn-primary:active { transform: none; }
}
/* Portada con carrusel */
.psite-hero { min-height: 88vh; min-height: 88svh; }
@media (min-width: 640px) { .psite-hero { min-height: 640px; height: 82vh; max-height: 820px; } }
.psite-slide { opacity: 0; transform: scale(1.06); transition: opacity 1.2s ease, transform 7s linear; }
.psite-slide-on { opacity: 1; transform: scale(1.0); }
.psite-hero-arrow { display: none; background: rgba(0,0,0,.28); backdrop-filter: blur(6px); transition: background .2s ease; }
@media (hover: hover) and (pointer: fine) and (min-width: 768px) {
  .psite-hero-arrow { display: block; }
  .psite-hero-arrow:hover { background: rgba(0,0,0,.5); }
}
.psite-hero-text > * { animation: psiteFadeUp .7s cubic-bezier(0.23, 1, 0.32, 1) both; }
.psite-hero-text > *:nth-child(2) { animation-delay: .08s; }
.psite-hero-text > *:nth-child(3) { animation-delay: .16s; }
.psite-hero-text > *:nth-child(4) { animation-delay: .24s; }
.psite-hero-text > *:nth-child(5) { animation-delay: .32s; }
.psite-gallery img { transition: transform .5s cubic-bezier(0.23, 1, 0.32, 1); }
@media (hover: hover) and (pointer: fine) { .psite-gallery a:hover img { transform: scale(1.05); } }
@media (prefers-reduced-motion: reduce) {
  .psite-slide { transition: opacity .6s ease; transform: none; }
  .psite-hero-text > * { animation: none; }
}
`
