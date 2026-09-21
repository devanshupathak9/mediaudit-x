"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, Shield, ArrowRight, AlertCircle } from "lucide-react";
import Button from "../components/ui/Button";
import { useRole } from "../contexts/RoleContext";

export default function LoginPage() {
  const router = useRouter();
  const { setRole } = useRole();
  const [credentials, setCredentials] = useState({
    username: "",
    password: "",
    role: "" as "hospital" | "insurance" | ""
  });
  const [loggingIn, setLoggingIn] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!credentials.username || !credentials.password || !credentials.role) {
      setError("Please fill in all fields");
      return;
    }

    // Validate credentials
    const validCredentials = {
      hospital: { username: "hospital", password: "demo" },
      insurance: { username: "insurance", password: "demo" }
    };

    if (
      credentials.username !== validCredentials[credentials.role].username ||
      credentials.password !== validCredentials[credentials.role].password
    ) {
      setError("Invalid username or password");
      return;
    }

    setLoggingIn(true);

    // Simulate authentication
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Set role and redirect to dashboard
    setRole(credentials.role);
    setLoggingIn(false);
    router.push("/");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600 text-white text-2xl font-bold mb-4">
            M
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">MediAudit-X</h1>
          <p className="text-slate-600">AI-Powered Clinical Claims Intelligence Platform</p>
        </div>

        {/* Login Form */}
        <div className="card p-8">
          <h2 className="text-xl font-semibold text-slate-900 mb-6 text-center">
            Sign In
          </h2>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-800">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={credentials.username}
                onChange={(e) => setCredentials(prev => ({ ...prev, username: e.target.value }))}
                placeholder="Enter username"
                className="input"
                disabled={loggingIn}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={credentials.password}
                onChange={(e) => setCredentials(prev => ({ ...prev, password: e.target.value }))}
                placeholder="Enter password"
                className="input"
                disabled={loggingIn}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Sign in as
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setCredentials(prev => ({ ...prev, role: "hospital" }))}
                  className={`flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all ${
                    credentials.role === "hospital"
                      ? "border-blue-600 bg-blue-50 text-blue-600"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  }`}
                  disabled={loggingIn}
                >
                  <Building2 size={24} />
                  <span className="text-sm font-medium">Hospital</span>
                </button>

                <button
                  type="button"
                  onClick={() => setCredentials(prev => ({ ...prev, role: "insurance" }))}
                  className={`flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all ${
                    credentials.role === "insurance"
                      ? "border-purple-600 bg-purple-50 text-purple-600"
                      : "border-slate-200 text-slate-600 hover:border-slate-300"
                  }`}
                  disabled={loggingIn}
                >
                  <Shield size={24} />
                  <span className="text-sm font-medium">Insurance</span>
                </button>
              </div>
            </div>

            <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-lg">
              <strong>Demo Credentials:</strong><br/>
              Hospital: username=<code>hospital</code>, password=<code>demo</code><br/>
              Insurance: username=<code>insurance</code>, password=<code>demo</code>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              loading={loggingIn}
              disabled={!credentials.username || !credentials.password || !credentials.role}
              className="w-full"
              icon={<ArrowRight size={18} />}
            >
              Sign In
            </Button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-sm text-slate-500">
          <p>Secure • Encrypted • HIPAA Compliant</p>
        </div>
      </div>
    </div>
  );
}
