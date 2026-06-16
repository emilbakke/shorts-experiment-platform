import { redirect } from "next/navigation";
import { studyBasePath } from "@/lib/study-session";

export default function StudyManosphereLegacyCompletePage() {
  redirect(`${studyBasePath}/complete`);
}
