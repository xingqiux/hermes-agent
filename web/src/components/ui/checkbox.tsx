import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: React.ReactNode;
  onCheckedChange?: (checked: boolean) => void;
}

export function Checkbox({
  className,
  label,
  id,
  checked,
  defaultChecked,
  onChange,
  onCheckedChange,
  ...props
}: CheckboxProps) {
  const isChecked = checked ?? defaultChecked ?? false;

  return (
    <label
      htmlFor={id}
      className={cn(
        "group flex items-center gap-2.5 cursor-pointer select-none",
        props.disabled && "cursor-not-allowed opacity-50",
      )}
    >
      <span
        className={cn(
          "flex h-4 w-4 shrink-0 items-center justify-center transition-all",
          "border bg-background/40",
          "group-has-[:focus-visible]:ring-2 group-has-[:focus-visible]:ring-ring group-has-[:focus-visible]:ring-offset-1",
          isChecked
            ? "border-foreground bg-foreground/20"
            : "border-border group-hover:border-foreground/40",
          className,
        )}
      >
        <Check
          className={cn(
            "h-3 w-3 transition-opacity",
            isChecked
              ? "text-foreground opacity-100"
              : "text-foreground opacity-0",
          )}
        />
      </span>
      <input
        type="checkbox"
        id={id}
        checked={checked}
        defaultChecked={checked === undefined ? defaultChecked : undefined}
        className="sr-only"
        onChange={(event) => {
          onChange?.(event);
          onCheckedChange?.(event.currentTarget.checked);
        }}
        {...props}
      />
      {label && <span className="text-sm">{label}</span>}
    </label>
  );
}
