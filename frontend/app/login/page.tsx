"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [tenant, setTenant] = useState("demo");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfa, setMfa] = useState("");
  const [mfaNeeded, setMfaNeeded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await api.login(tenant, email, password, mfa || undefined)
          : await api.register(tenant, email, password);
      if (res.mfa_required) {
        setMfaNeeded(true);
        setError("Code d’authentification (MFA) requis.");
        return;
      }
      setToken(res.access_token);
      router.push("/");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto mt-16">
      {/* Surface publique : le logotype complet, pas le monogramme. */}
      <div className="text-center mb-6 space-y-2">
        <div className="inline-flex items-center gap-2.5">
          <span className="grid place-items-center w-9 h-9 rounded-button bg-ink text-white font-mono text-metric leading-none">
            N
          </span>
          <span className="text-title text-ink tracking-tight">Noreon</span>
        </div>
        <div className="text-body text-ink-3">
          Un outil rigoureux dont les réponses se lisent comme un rapport d'analyste.
        </div>
      </div>

      <div className="card p-6 space-y-5 shadow-e2">
        <div className="flex gap-2">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`btn flex-1 ${
                mode === m ? "bg-brand-600 text-white" : "bg-raised border border-line text-ink-2 hover:border-line-strong"
              }`}
            >
              {m === "login" ? "Connexion" : "Créer l'espace"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          <Field label="Entreprise (tenant)" value={tenant} onChange={setTenant} mono />
          <Field label="Email" value={email} onChange={setEmail} type="email" />
          <Field label="Mot de passe" value={password} onChange={setPassword} type="password" />
          {mfaNeeded && (
            <Field label="Code MFA (6 chiffres)" value={mfa} onChange={setMfa} mono />
          )}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Se connecter" : "Créer l'administrateur"}
          </button>
        </form>

        {error && (
          <div className="state state-abstain">
            <div className="state-title">À compléter</div>
            <div className="state-body">{error}</div>
          </div>
        )}
        {mode === "register" && (
          <p className="text-small text-ink-3">
            Crée le premier compte (administrateur) d'un nouvel espace entreprise.
          </p>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="field-label">{label}</label>
      <input
        className={`field ${mono ? "mono" : ""}`}
        type={type}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
