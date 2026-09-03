"use client";

import { useEffect, useState } from "react";
import { api, Me } from "@/lib/api";
import ExecutiveHome from "@/components/home/ExecutiveHome";
import AnalystHome from "@/components/home/AnalystHome";

// Accueil selon le rôle (écrans 01–02). Le périmètre filtre ce qui est mis en
// avant, jamais les chiffres eux-mêmes.
//   admin / reader → accueil dirigeant (décider)
//   analyst        → accueil analyste (vérifier)
//
// On n'attend pas la résolution de la session : l'accueil dirigeant s'affiche
// tout de suite, et bascule vers l'analyste si le rôle le demande.
export default function Home() {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null));
  }, []);

  const name = me?.email
    ? me.email.split("@")[0].split(/[.\-_]/)[0].replace(/^./, (c) => c.toUpperCase())
    : "";

  if (me?.role === "analyst") return <AnalystHome name={name} />;
  return <ExecutiveHome name={name} />;
}
