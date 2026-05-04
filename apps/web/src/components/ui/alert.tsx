export function Alert({
  variant,
  title,
  children,
}: {
  variant: "info" | "warning" | "error";
  title: string;
  children?: React.ReactNode;
}) {
  const map = {
    info: "border-cyan-200 bg-cyan-50 text-cyan-950",
    warning: "border-amber-200 bg-amber-50 text-amber-950",
    error: "border-red-200 bg-red-50 text-red-950",
  } as const;
  return (
    <div className={`rounded-xl border p-4 ${map[variant]}`}>
      <p className="text-sm font-semibold">{title}</p>
      {children ? <div className="mt-2 text-sm opacity-90">{children}</div> : null}
    </div>
  );
}
