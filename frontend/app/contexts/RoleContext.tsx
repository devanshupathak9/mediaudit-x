"use client";

import { createContext, useContext, useState, ReactNode } from "react";

export type UserRole = "hospital" | "insurance";

interface RoleContextType {
  role: UserRole | null;
  setRole: (role: UserRole) => void;
  logout: () => void;
  userName: string;
  userTitle: string;
  isAuthenticated: boolean;
}

const RoleContext = createContext<RoleContextType | undefined>(undefined);

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole | null>(null); // Start with no role - requires login
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const userName = role === "hospital" ? "CityCare Hospital" : "Dr. Sarah Mitchell";
  const userTitle = role === "hospital" ? "Hospital Administrator" : "Insurance Reviewer";

  const setRoleWithAuth = (newRole: UserRole) => {
    setRole(newRole);
    setIsAuthenticated(true);
  };

  const logout = () => {
    setRole(null);
    setIsAuthenticated(false);
  };

  return (
    <RoleContext.Provider value={{ role, setRole: setRoleWithAuth, logout, userName, userTitle, isAuthenticated }}>
      {children}
    </RoleContext.Provider>
  );
}

export function useRole() {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error("useRole must be used within RoleProvider");
  }
  return context;
}
