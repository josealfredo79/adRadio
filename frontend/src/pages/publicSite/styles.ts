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
.psite-nav-link:hover {
  opacity: 1;
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
.psite-mobile-link:hover {
  background-color: rgba(127,127,127,.1);
}
@keyframes psiteFadeUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.psite-hover-lift {
  transition: transform .3s ease, box-shadow .3s ease;
}
.psite-hover-lift:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 32px -12px var(--psite-glow, rgba(0,0,0,.35));
}
.psite-btn-primary {
  transition: transform .3s ease, box-shadow .3s ease;
}
.psite-btn-primary:hover {
  transform: scale(1.03);
  box-shadow: 0 12px 28px -8px var(--psite-glow, rgba(0,0,0,.35));
}
.psite-btn-primary:active {
  transform: scale(.98);
}
`
