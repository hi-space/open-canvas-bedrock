"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Page() {
  const router = useRouter();

  useEffect(() => {
    // Authentication disabled - just redirect
    router.push("/");
  }, [router]);

  return <p>Redirecting...</p>;
}
