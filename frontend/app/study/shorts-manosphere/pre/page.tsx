import { redirect } from "next/navigation";
import { studyBasePath } from "@/lib/study-session";

export default function StudyManosphereLegacyPrePage() {
  redirect(`${studyBasePath}/pre`);
}
