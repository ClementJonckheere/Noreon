import DomainLanding from "@/components/DomainLanding";
export default function DiscoveriesPage() {
  return (
    <DomainLanding
      title="Découvertes"
      lead="Ce que Noreon a trouvé sans qu'on le demande — signaux à confirmer, investiguer ou écarter."
      emptyTitle="Aucune découverte pour l'instant"
      emptyBody="Les découvertes apparaissent quand une source est analysée. Connectez une source et posez une première question."
      cta={{ href: "/data", label: "Voir les données" }}
    />
  );
}
