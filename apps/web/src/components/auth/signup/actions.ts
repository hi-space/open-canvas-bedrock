"use server";

import { redirect } from "next/navigation";
import { SignupWithEmailInput } from "./Signup";

export async function signup(input: SignupWithEmailInput, baseUrl: string) {
  // Authentication disabled
  redirect("/auth/signup?error=true");
}
