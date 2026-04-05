import type { SVGProps } from "react";

export function SpinnerIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      className={["animate-spin h-5 w-5 shrink-0", className].filter(Boolean).join(" ")}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      {...props}
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
