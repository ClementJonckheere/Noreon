"use client";
import { useParams } from "next/navigation";
import ConversationScreen from "@/components/conversation/ConversationScreen";

export default function ConversationPage() {
  const params = useParams();
  return <ConversationScreen id={String(params.id)} />;
}
