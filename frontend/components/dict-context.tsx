"use client";

import { createContext, useContext } from "react";
import { getDict, DEFAULT_LANG, type Dict } from "@/app/dictionaries";

const DictContext = createContext<Dict>(getDict(DEFAULT_LANG));

export function DictProvider({ value, children }: { value: Dict; children: React.ReactNode }) {
  return <DictContext.Provider value={value}>{children}</DictContext.Provider>;
}

export const useDict = () => useContext(DictContext);
