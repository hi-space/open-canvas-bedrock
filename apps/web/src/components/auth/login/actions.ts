"use server";

import { redirect } from "next/navigation";
import { LoginWithEmailInput } from "./Login";

export async function login(input: LoginWithEmailInput) {
  // Authentication disabled
  redirect("/auth/login?error=true");
}
