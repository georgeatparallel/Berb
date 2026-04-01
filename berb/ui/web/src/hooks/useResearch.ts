/**
 * Research submission hook
 * Manages research job creation and progress tracking
 */

import { useState, useEffect, useCallback } from 'react';
import { apiClient, type ResearchJob, type CreateResearchRequest } from '@utils/api';

interface UseResearchResult {
  job: ResearchJob | null;
  isLoading: boolean;
  error: string | null;
  submitResearch: (request: CreateResearchRequest) => Promise<void>;
  cancelJob: () => void;
  refreshStatus: () => Promise<void>;
}

export function useResearch(): UseResearchResult {
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Submit new research job
   */
  const submitResearch = useCallback(async (request: CreateResearchRequest) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await apiClient.createResearch(request);
      
      setJob({
        id: response.id,
        topic: response.topic,
        preset: request.preset,
        mode: request.mode || 'autonomous',
        status: response.status as ResearchJob['status'],
        progress: response.progress || 0,
        current_stage: 1,
      });

      console.log('Research job created:', response.id);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMessage);
      console.error('Failed to submit research:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Refresh job status
   */
  const refreshStatus = useCallback(async () => {
    if (!job?.id) return;

    try {
      const status = await apiClient.getResearchStatus(job.id);
      setJob(status);
    } catch (err) {
      console.error('Failed to refresh status:', err);
    }
  }, [job?.id]);

  /**
   * Cancel current job
   */
  const cancelJob = useCallback(() => {
    setJob(null);
    setError(null);
  }, []);

  /**
   * Poll for status updates
   */
  useEffect(() => {
    if (!job?.id || job.status === 'completed' || job.status === 'failed') {
      return;
    }

    // Poll every 2 seconds
    const pollInterval = setInterval(() => {
      refreshStatus();
    }, 2000);

    return () => {
      clearInterval(pollInterval);
    };
  }, [job?.id, job?.status, refreshStatus]);

  return {
    job,
    isLoading,
    error,
    submitResearch,
    cancelJob,
    refreshStatus,
  };
}
