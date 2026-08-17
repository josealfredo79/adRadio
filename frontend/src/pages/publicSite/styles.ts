export const PUBLIC_SITE_STYLES = `
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
