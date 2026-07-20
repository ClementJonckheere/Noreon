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
      <div className="card p-6 space-y-5">
        <div className="text-center">
          <div className="text-2xl font-bold">Noreon</div>
          <div className="text-xs text-noreon-soft">Comprendre. Relier. Éclairer.</div>
        </div>

        <div className="flex gap-2 text-sm">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`btn flex-1 justify-center ${
                mode === m ? "bg-noreon-accent text-white" : "border border-noreon-border text-noreon-soft"
              }`}
            >
              {m === "login" ? "Connexion" : "Créer l’espace"}
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
          <button className="btn-primary w-full justify-center" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Se connecter" : "Créer l’administrateur"}
          </button>
        </form>

        {error && (
          <div className="text-sm text-amber-700 bg-amber-500/10 rounded-lg p-3">{error}</div>
        )}
        {mode === "register" && (
          <p className="text-xs text-noreon-soft">
            Crée le premier compte (administrateur) d’un nouvel espace entreprise.
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
      <label className="text-xs text-noreon-soft">{label}</label>
      <input
        className={`input ${mono ? "mono" : ""}`}
        type={type}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
