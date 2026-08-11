export interface Ticket {
  id: number;
  ticket_code: string;
  subject: string;
  description: string;
  category: string | null;
  priority: string | null;
  suggested_reply: string | null;
  status: string;
  created_at: string;
}

export interface AnalyticsData {
  category_counts: Record<string, number>;
  priority_counts: Record<string, number>;
}
