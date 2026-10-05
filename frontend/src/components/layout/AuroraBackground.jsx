export function AuroraBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -left-[20%] -top-[30%] size-[65vmax] rounded-full bg-saffron/25 blur-[110px] animate-drift dark:bg-saffron/12" />
      <div className="absolute -right-[20%] top-[10%] size-[60vmax] rounded-full bg-navy/25 blur-[120px] animate-drift [animation-delay:-13s] dark:bg-accent/15" />
      <div className="absolute -bottom-[35%] left-[15%] size-[60vmax] rounded-full bg-indgreen/20 blur-[120px] animate-drift [animation-delay:-26s] dark:bg-indgreen/10" />
      <div className="absolute inset-0 [background-image:radial-gradient(rgb(15_23_42/.07)_1px,transparent_1px)] [background-size:24px_24px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)] dark:[background-image:radial-gradient(rgb(255_255_255/.06)_1px,transparent_1px)]" />
    </div>
  );
}
