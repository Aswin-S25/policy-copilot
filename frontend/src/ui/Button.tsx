import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const base =
  "inline-flex items-center justify-center gap-2 font-medium whitespace-nowrap " +
  "rounded-control transition-colors duration-150 select-none " +
  "disabled:cursor-not-allowed disabled:opacity-50";

const variants: Record<Variant, string> = {
  primary:
    "bg-accent text-white hover:bg-accent-hover active:bg-accent-ink",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-sunken hover:border-line-strong",
  ghost: "text-ink-soft hover:bg-sunken hover:text-ink",
  danger: "bg-danger text-white hover:bg-[#931c13]",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-ui",
  md: "h-9 px-3.5 text-control",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", icon, className = "", children, type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: icon-only buttons need an accessible name. */
  label: string;
  variant?: "ghost" | "primary";
  size?: "sm" | "md";
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = "ghost", size = "md", className = "", children, type = "button", ...props },
  ref,
) {
  const tone =
    variant === "primary"
      ? "bg-accent text-white hover:bg-accent-hover disabled:bg-line-strong disabled:text-white"
      : "text-muted hover:bg-sunken hover:text-ink";
  const box = size === "sm" ? "size-7" : "size-8";

  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={
        `inline-flex shrink-0 items-center justify-center rounded-control transition-colors ` +
        `duration-150 disabled:cursor-not-allowed ${tone} ${box} ${className}`
      }
      {...props}
    >
      {children}
    </button>
  );
});
