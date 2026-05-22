import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
type ButtonSize = "default" | "sm" | "lg" | "icon";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClasses: Record<ButtonVariant, string> = {
  default: "bg-slate-900 text-white shadow-sm shadow-black/10 hover:bg-slate-800",
  destructive: "bg-red-600 text-white shadow-sm shadow-black/10 hover:bg-red-500",
  outline: "border border-slate-200 bg-white text-slate-900 shadow-sm shadow-black/5 hover:bg-slate-50",
  secondary: "bg-slate-200 text-slate-900 shadow-sm shadow-black/5 hover:bg-slate-300",
  ghost: "text-slate-900 hover:bg-slate-100",
  link: "text-slate-900 underline-offset-4 hover:underline"
};

const sizeClasses: Record<ButtonSize, string> = {
  default: "h-9 px-4 py-2",
  sm: "h-8 rounded-lg px-3 text-xs",
  lg: "h-10 rounded-lg px-8",
  icon: "h-9 w-9"
};

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-colors outline-offset-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-slate-400/70 disabled:pointer-events-none disabled:opacity-50",
          variantClasses[variant],
          sizeClasses[size],
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
