export interface SearchResponse {
  status: string;
  request_id: string;
  graph_node_ids: string[];
  merged_data: Record<string, unknown>;
  completeness_score: number;
  error_message?: string;
}

export interface GraphNode {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  from_node_id: string;
  to_node_id: string;
  edge_type: string;
  properties: Record<string, unknown>;
}

export interface GraphTraversalResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  depth_reached: number;
  truncated: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ActivityItem {
  id: string;
  type: string;
  timestamp: string;
  description: string;
  metadata: Record<string, unknown>;
}

export interface ActivityResponse {
  activities: ActivityItem[];
  total: number;
}

export interface FeedbackRequest {
  node_id: string;
  feedback_type: string;
  feedback_value: number;
  comment?: string;
}

export interface User {
  id: string;
  username: string;
  email: string;
}

export interface NLQueryResponse {
  answer: string;
  data: unknown[];
}

export interface ExplosionResponse {
  status: string;
  new_nodes_added: number;
  new_edges_added: number;
  total_nodes: number;
  total_edges: number;
}
