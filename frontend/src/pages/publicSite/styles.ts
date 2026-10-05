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
`
