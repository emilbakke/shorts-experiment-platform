import { redirect } from "next/navigation";
import { studyBasePath } from "@/lib/study-session";

export default function StudyManosphereLegacyPostPage() {
  redirect(`${studyBasePath}/post`);
}
