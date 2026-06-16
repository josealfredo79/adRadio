import SEO from '@/components/SEO'
import LandingNav from './components/LandingNav'
import HeroSection from './components/HeroSection'
import ProblemSection from './components/ProblemSection'
import HowItWorksSection from './components/HowItWorksSection'
import FeaturesSection from './components/FeaturesSection'
import AIAgentSection from './components/AIAgentSection'
import TestimonialsSection from './components/TestimonialsSection'
import PricingSection from './components/PricingSection'
import IntegrationsSection from './components/IntegrationsSection'
import FaqSection from './components/FaqSection'
import CtaSection from './components/CtaSection'
import LandingFooter from './components/LandingFooter'

export default function LandingPage() {
  return (
    <>
      <SEO />
      <div className="min-h-screen bg-[#06060f] text-white font-sans overflow-x-hidden">
        <style>{`
          @keyframes fadeUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
          }
          @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-12px); }
          }
          @keyframes shimmer {
            0% { background-position: -200% center; }
            100% { background-position: 200% center; }
          }
          .text-shimmer {
            background: linear-gradient(90deg, #674CC4, #6366f1, #a855f7, #674CC4);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: shimmer 4s linear infinite;
          }
          .float-anim { animation: float 4s ease-in-out infinite; }
          .glow-purple { box-shadow: 0 0 60px rgba(124,58,237,0.3); }
          .glow-green { box-shadow: 0 0 40px rgba(34,197,94,0.2); }
          .glass {
            background: rgba(255,255,255,0.04);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.08);
          }
          .mesh-bg {
            background:
              radial-gradient(ellipse 80% 50% at 20% 10%, rgba(124,58,237,0.18) 0%, transparent 60%),
              radial-gradient(ellipse 60% 40% at 80% 80%, rgba(99,102,241,0.14) 0%, transparent 60%),
              radial-gradient(ellipse 50% 50% at 50% 50%, rgba(168,85,247,0.08) 0%, transparent 60%);
          }
          .mesh-bg-light {
            background:
              radial-gradient(ellipse 80% 50% at 20% 10%, rgba(124,58,237,0.08) 0%, transparent 60%),
              radial-gradient(ellipse 60% 40% at 80% 80%, rgba(99,102,241,0.06) 0%, transparent 60%);
          }
        `}</style>

        <LandingNav />
        <HeroSection />
        <ProblemSection />
        <HowItWorksSection />
        <FeaturesSection />
        <AIAgentSection />
        <TestimonialsSection />
        <PricingSection />
        <IntegrationsSection />
        <FaqSection />
        <CtaSection />
        <LandingFooter />
      </div>
    </>
  )
}
