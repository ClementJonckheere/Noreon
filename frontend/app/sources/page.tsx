import { redirect } from "next/navigation";
// Les sources sont désormais un drill-down sous « Données ».
export default function SourcesRedirect() {
  redirect("/data");
}
