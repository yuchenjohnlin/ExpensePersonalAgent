import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Join class names; when two Tailwind classes clash (px-2 and px-4), the later one wins. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
