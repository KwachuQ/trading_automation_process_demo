import { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../api';

export function useLiveSession() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  // Tracks the setup_type that was last explicitly marked as active.
  const [activeSetupType, setActiveSetupType] = useState(null);

  const fetchLiveSession = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/session/live`);
      if (!res.ok) throw new Error('Failed to fetch live session data');
      const result = await res.json();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchScenarios = useCallback(async (dateStr) => {
    try {
      const res = await fetch(`${API_BASE}/session/scenarios/${dateStr}`);
      if (!res.ok) throw new Error('Failed to fetch scenarios');
      const result = await res.json();
      setScenarios(result);
    } catch (err) {
      console.error(err);
    }
  }, []);

  const saveScenarios = useCallback(async (dateStr, scenarioList) => {
    try {
      const res = await fetch(`${API_BASE}/session/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_date: dateStr,
          scenarios: scenarioList
        })
      });
      if (!res.ok) throw new Error('Failed to save scenarios');
      const result = await res.json();
      setScenarios(result);
    } catch (err) {
      console.error(err);
      throw err;
    }
  }, []);

  const deleteScenario = useCallback(async (dateStr, scenarioNumber) => {
    try {
      const res = await fetch(`${API_BASE}/session/scenarios/${dateStr}/${scenarioNumber}`, {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error('Failed to delete scenario');
      await fetchScenarios(dateStr);
    } catch (err) {
      console.error(err);
    }
  }, [fetchScenarios]);

  /**
   * Posts the chosen setup_type to the backend active-setup log so the
   * auto-tagger can correlate trades with the correct setup post-session.
   * Uses optimistic update: the local state changes immediately; if the
   * request fails the error surfaces via console and the state is reverted.
   */
  const markActiveSetup = useCallback(async (setupType) => {
    const previous = activeSetupType;
    // Optimistic update.
    setActiveSetupType(setupType);
    try {
      const res = await fetch(`${API_BASE}/session/active-setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ setup_type: setupType }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      console.error('Failed to mark active setup:', err);
      // Revert optimistic update on failure.
      setActiveSetupType(previous);
    }
  }, [activeSetupType]);

  /**
   * Re-hydrates activeSetupType from the backend on mount.
   * Called once when SessionDashboard mounts so that navigating away
   * and back does not lose the "Mark as Active" state.
   */
  const fetchActiveSetup = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/session/active-setup`);
      if (!res.ok) return;
      const { setup_type } = await res.json();
      setActiveSetupType(setup_type ?? null);
    } catch (err) {
      console.error('Failed to fetch active setup:', err);
    }
  }, []);

  useEffect(() => {
    fetchLiveSession();
    fetchActiveSetup();
    const interval = setInterval(fetchLiveSession, 120000); // 120s
    return () => clearInterval(interval);
  }, [fetchLiveSession, fetchActiveSetup]);


  return {
    data,
    setupScores: data?.setup_scores || [],
    loading,
    error,
    scenarios,
    activeSetupType,
    fetchLiveSession,
    fetchScenarios,
    saveScenarios,
    deleteScenario,
    markActiveSetup,
  };
}
