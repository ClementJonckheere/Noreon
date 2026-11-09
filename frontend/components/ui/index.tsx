// Couche de primitives (handoff §3). Une primitive par section, avec exactement
// les variantes et états décrits — ni plus, ni moins. Toutes s'appuient sur les
// classes de globals.css (aucune couleur en dur ici non plus).
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/* -- Bouton -------------------------------------------------------------- */
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
type BtnSize = "sm" | "md" | "lg";
const BTN_VARIANT: Record<BtnVariant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  danger: "btn-danger",
};
const BTN_SIZE: Record<BtnSize, string> = { sm: "btn-sm", md: "", lg: "btn-lg" };

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className = "",
  children,
  disabled,
  ...rest
}: {
  variant?: BtnVariant;
  size?: BtnSize;
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`${BTN_VARIANT[variant]} ${BTN_SIZE[size]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span className="w-[9px] h-[9px] rounded-full border-[1.5px] border-ink-tertiary border-t-transparent animate-spin" />
      )}
      {children}
    </button>
  );
}

/* -- Champ --------------------------------------------------------------- */
export function Input({
  label,
  mono,
  className = "",
  ...rest
}: { label?: string; mono?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  const el = <input className={`field ${mono ? "mono" : ""} ${className}`} {...rest} />;
  if (!label) return el;
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      {el}
    </label>
  );
}

/* -- Badge / étiquette d'état -------------------------------------------- */
type Tone = "brand" | "reason" | "success" | "warning" | "blocker" | "neutral";
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`tag tag-${tone}`}>{children}</span>;
}

/* -- Bloc d'état — les quatre seuls -------------------------------------- */
type StateKind = "limit" | "abstain" | "blocker" | "validate";
const STATE_LABEL: Record<StateKind, string> = {
  limit: "Limite",
  abstain: "Abstention",
  blocker: "Blocage",
  validate: "Validation",
};
export function StatusBlock({
  kind,
  title,
  children,
}: {
  kind: StateKind;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`state state-${kind}`}>
      <div className="state-title">{title ?? STATE_LABEL[kind]}</div>
      <div className="state-body">{children}</div>
    </div>
  );
}

/* -- Barre de confiance — TOUJOURS violette (jamais verte). --------------
   Sous le seuil : remplissage orange + repère de seuil de publication.      */
export function ConfidenceBar({
  percent,
  threshold = 75,
  label = "Confiance de la conclusion",
}: {
  percent: number;
  threshold?: number;
  label?: string;
}) {
  const below = percent < threshold;
  const pct = Math.max(0, Math.min(100, percent));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className={`text-label uppercase ${below ? "text-ink-secondary" : "text-ink-tertiary"}`}>
          {label}
        </span>
        <span className={`metric ${below ? "text-warning-hover" : "text-reasoning"}`}>{percent}%</span>
      </div>
      <div className="relative">
        <div className="confidence-track">
          <div className={`confidence-fill ${below ? "confidence-fill-below" : ""}`} style={{ width: `${pct}%` }} />
        </div>
        <div
          className="absolute -top-[3px] h-[11px] w-px bg-ink-secondary"
          style={{ left: `${threshold}%` }}
        />
      </div>
      <div className="text-label uppercase text-ink-tertiary">
        Seuil de publication {threshold}%
      </div>
    </div>
  );
}

/* -- Timeline verticale (progression / chaîne d'investigation) ----------- */
export type Step = { label: string; status: "done" | "current" | "todo"; meta?: string };
export function Timeline({ steps }: { steps: Step[] }) {
  return (
    <ol className="relative">
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        return (
          <li key={i} className="flex gap-3 pb-[13px] last:pb-0">
            <div className="flex flex-col items-center">
              {s.status === "done" && <span className="w-2 h-2 rounded-full bg-success" />}
              {s.status === "current" && <span className="w-[9px] h-[9px] rounded-full bg-reasoning" />}
              {s.status === "todo" && <span className="w-2 h-2 rounded-full border-[1.5px] border-line-strong" />}
              {!last && <span className="w-px flex-1 min-h-[18px] bg-line-subtle mt-1" />}
            </div>
            <div className="pb-1 -mt-0.5">
              <div
                className={`text-[12.5px] ${
                  s.status === "current" ? "text-reasoning-hover font-medium" : s.status === "todo" ? "text-ink-tertiary" : "text-ink-secondary"
                }`}
              >
                {s.label}
              </div>
              {s.meta && <div className="meta">{s.meta}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
