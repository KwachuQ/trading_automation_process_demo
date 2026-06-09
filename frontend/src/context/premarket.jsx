import { createContext, useContext, useState, useMemo } from 'react'

const today = new Date().toISOString().slice(0, 10)

export const PreMarketContext = createContext(null)

export function PreMarketProvider({ children }) {
  const [pipelineStatus, setPipelineStatus] = useState('pending')
  const value = useMemo(
    () => ({ pipelineStatus, setPipelineStatus, today }),
    [pipelineStatus]
  )
  return <PreMarketContext.Provider value={value}>{children}</PreMarketContext.Provider>
}

export function usePreMarket() {
  return useContext(PreMarketContext)
}
