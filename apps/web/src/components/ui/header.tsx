import { cn } from "@/lib/utils";

export function TighterText({
  className,
  children,
  as: Component = "p",
}: {
  className?: string;
  children: React.ReactNode;
  as?: "p" | "span" | "div";
}) {
  return <Component className={cn("tracking-tighter", className)}>{children}</Component>;
}
