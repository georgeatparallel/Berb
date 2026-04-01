/**
 * Berb API Client
 * Connects to FastAPI backend for research pipeline execution
 * Uses Vite proxy to avoid CORS issues
 */

// Use relative URL - Vite will proxy to backend
const API_BASE_URL = '/api';

export interface ResearchJob {
  id: string;
  topic: string;
  preset?: string;
  mode: 'autonomous' | 'collaborative';
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  current_stage?: number;
  result?: {
    run_dir: string;
    stages_completed: number;
  };
  error?: string;
}

export interface CreateResearchRequest {
  topic: string;
  preset?: string;
  mode?: 'autonomous' | 'collaborative';
  budget_usd?: number;
}

export interface CreateResearchResponse {
  id: string;
  status: string;
  topic: string;
  progress?: number;
}

export class BerbApiClient {
  private static instance: BerbApiClient;

  private constructor() {}

  public static getInstance(): BerbApiClient {
    if (!BerbApiClient.instance) {
      BerbApiClient.instance = new BerbApiClient();
    }
    return BerbApiClient.instance;
  }

  /**
   * Create a new research job
   */
  async createResearch(
    request: CreateResearchRequest
  ): Promise<CreateResearchResponse> {
    try {
      const response = await fetch(`${API_BASE_URL}/v1/research`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          topic: request.topic,
          preset: request.preset || 'humanities',
          mode: request.mode || 'autonomous',
          budget_usd: request.budget_usd || 1.0,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create research job');
      }

      return await response.json();
    } catch (error) {
      console.error('Error creating research job:', error);
      throw error;
    }
  }

  /**
   * Get research job status
   */
  async getResearchStatus(jobId: string): Promise<ResearchJob> {
    try {
      const response = await fetch(`${API_BASE_URL}/v1/research/${jobId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to get job status');
      }

      return await response.json();
    } catch (error) {
      console.error('Error getting research status:', error);
      throw error;
    }
  }

  /**
   * Stream research progress via SSE
   */
  streamProgress(
    jobId: string,
    onProgress: (data: any) => void,
    onComplete?: () => void
  ): () => void {
    const eventSource = new EventSource(
      `${API_BASE_URL}/api/v1/research/${jobId}/stream`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onProgress(data);
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    };

    eventSource.onerror = () => {
      console.error('SSE connection error');
      eventSource.close();
      if (onComplete) {
        onComplete();
      }
    };

    // Return cleanup function
    return () => {
      eventSource.close();
    };
  }

  /**
   * Get available presets
   */
  async getPresets(): Promise<string[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/presets`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch presets');
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching presets:', error);
      return ['humanities', 'ml-conference', 'physics', 'social-sciences'];
    }
  }

  /**
   * Check API health
   */
  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/healthz`, {
        method: 'GET',
      });
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }
}

// Export singleton instance
export const apiClient = BerbApiClient.getInstance();
