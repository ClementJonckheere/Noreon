import DomainLanding from "@/components/DomainLanding";
export default function PlanPage() {
  return (
    <DomainLanding
      title="Plan d'action"
      lead="Ce qu'on décide de faire — les décisions retenues, leur mise en œuvre et l'effet mesuré."
      emptyTitle="Aucune action retenue"
      emptyBody="Une décision entre ici quand vous la retenez depuis une réponse d'analyse."
      cta={{ href: "/", label: "Composer une analyse" }}
    />
  );
}
