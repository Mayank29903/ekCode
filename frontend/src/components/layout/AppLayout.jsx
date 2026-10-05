import { Suspense, useState } from "react";
import { Outlet, useLocation } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { AuroraBackground } from "./AuroraBackground";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { CommandPalette } from "./CommandPalette";
import { FullScreenLoader } from "../ui/Skeleton";
import { useHotkeys } from "../../hooks/useHotkeys";

export default function AppLayout() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const location = useLocation();
  useHotkeys({ "mod+k": () => setPaletteOpen((v) => !v) });

  return (
    <div className="flex min-h-full">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-white">Skip to content</a>
      <AuroraBackground />
      <Sidebar mobileOpen={mobileNav} onClose={() => setMobileNav(false)} />
      <div className="flex min-w-0 flex-1 flex-col lg:pl-72">
        <Topbar onOpenPalette={() => setPaletteOpen(true)} onOpenNav={() => setMobileNav(true)} />
        <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 pb-16 pt-4 md:px-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -6, filter: "blur(2px)" }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <Suspense fallback={<FullScreenLoader />}>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
