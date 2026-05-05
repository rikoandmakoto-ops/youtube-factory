import { ReactNode } from 'react';

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: ReactNode;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="label">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}

export function Section({
  title,
  description,
  defaultOpen = false,
  children,
}: {
  title: string;
  description?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="card group" open={defaultOpen}>
      <summary className="cursor-pointer list-none flex items-center justify-between">
        <div>
          <h2 className="font-bold text-slate-100">{title}</h2>
          {description && (
            <p className="text-xs text-slate-500 mt-1">{description}</p>
          )}
        </div>
        <span
          aria-hidden
          className="text-slate-400 group-open:rotate-180 transition"
        >
          ▾
        </span>
      </summary>
      <div className="mt-4 space-y-4">{children}</div>
    </details>
  );
}

export function Row({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (b: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex items-start gap-3 select-none cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-5 h-5 mt-0.5 accent-accent shrink-0"
      />
      <div>
        <span className="block">{label}</span>
        {description && (
          <span className="block text-xs text-slate-500 mt-0.5">
            {description}
          </span>
        )}
      </div>
    </label>
  );
}

export function NumberField({
  value,
  onChange,
  min,
  max,
  step = 1,
  id,
  unit,
}: {
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max?: number;
  step?: number;
  id?: string;
  unit?: string;
}) {
  return (
    <div className="relative">
      <input
        id={id}
        type="number"
        value={Number.isFinite(value) ? value : ''}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const v = e.target.value === '' ? NaN : Number(e.target.value);
          onChange(v);
        }}
        className="input"
      />
      {unit && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500 pointer-events-none">
          {unit}
        </span>
      )}
    </div>
  );
}

export function ColorField({
  value,
  onChange,
}: {
  value: [number, number, number];
  onChange: (c: [number, number, number]) => void;
}) {
  const hex =
    '#' +
    value
      .map((n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0'))
      .join('');
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={hex}
        onChange={(e) => {
          const h = e.target.value.replace('#', '');
          const r = parseInt(h.slice(0, 2), 16);
          const g = parseInt(h.slice(2, 4), 16);
          const b = parseInt(h.slice(4, 6), 16);
          onChange([r, g, b]);
        }}
        className="w-12 h-10 rounded-lg border border-border bg-bg-elev cursor-pointer"
      />
      <code className="text-xs text-slate-400">
        rgb({value[0]},{value[1]},{value[2]})
      </code>
    </div>
  );
}
