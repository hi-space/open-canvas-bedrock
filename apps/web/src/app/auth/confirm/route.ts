import { redirect } from "next/navigation";

export async function GET() {
  // Authentication disabled
  redirect("/error");
}
