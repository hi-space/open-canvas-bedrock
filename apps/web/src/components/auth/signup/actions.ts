"use server";

import { redirect } from "next/navigation";
import { SignupWithEmailInput } from "./Signup";

export async function signup(_input: SignupWithEmailInput, _baseUrl: string) {
  // Authentication disabled
  redirect("/auth/signup?error=true");
}
