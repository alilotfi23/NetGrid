import Link from "next/link";

import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 dark:bg-black">
      <div className="w-full max-w-sm">
        <div className="rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            NetGrid
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Sign in to the admin dashboard.
          </p>
          <div className="mt-6">
            <LoginForm />
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-zinc-400 dark:text-zinc-500">
          Dev seed credentials: <code>superadmin</code> / <code>netgrid-admin</code> —{" "}
          <Link href="/" className="underline hover:text-zinc-600 dark:hover:text-zinc-300">
            back to dashboard
          </Link>
        </p>
      </div>
    </main>
  );
}
