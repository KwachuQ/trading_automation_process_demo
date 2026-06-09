import { useState, useEffect, useCallback } from 'react';
import api from '../api';

export function useFeatureStore() {
  const [marketScenarios, setMarketScenarios] = useState([]);
  const [scoringCriteria, setScoringCriteria] = useState([]);
  const [setupTypeFilter, setSetupTypeFilter] = useState('All');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const criteriaUrl = setupTypeFilter && setupTypeFilter !== 'All'
        ? `/feature-store/scoring?setup_type=${setupTypeFilter}`
        : '/feature-store/scoring';
      const [scenariosRes, criteriaRes] = await Promise.all([
        api.get('/feature-store/scenarios'),
        api.get(criteriaUrl)
      ]);
      setMarketScenarios(scenariosRes.data);
      setScoringCriteria(criteriaRes.data);
    } catch (err) {
      setError('Failed to fetch feature store data');
    } finally {
      setLoading(false);
    }
  }, [setupTypeFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const _executeAction = async (actionFn, errorMsg) => {
    setLoading(true);
    try {
      await actionFn();
      await fetchData();
    } catch (err) {
      setError(err.response?.data?.detail || errorMsg);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const createScenario = (scenario) => _executeAction(() => api.post('/feature-store/scenarios', scenario), 'Failed to create scenario');
  const updateScenario = (id, scenario) => _executeAction(() => api.put(`/feature-store/scenarios/${id}`, scenario), 'Failed to update scenario');
  const deleteScenario = (id) => _executeAction(() => api.delete(`/feature-store/scenarios/${id}`), 'Failed to delete scenario');

  const createCriterion = (criterion) => _executeAction(() => api.post('/feature-store/scoring', criterion), 'Failed to create criterion');
  const updateCriterion = (id, criterion) => _executeAction(() => api.put(`/feature-store/scoring/${id}`, criterion), 'Failed to update criterion');
  const deleteCriterion = (id) => _executeAction(() => api.delete(`/feature-store/scoring/${id}`), 'Failed to delete criterion');

  return {
    marketScenarios,
    scoringCriteria,
    setupTypeFilter,
    setSetupTypeFilter,
    loading,
    error,
    createScenario,
    updateScenario,
    deleteScenario,
    createCriterion,
    updateCriterion,
    deleteCriterion,
    refresh: fetchData,
  };
}
