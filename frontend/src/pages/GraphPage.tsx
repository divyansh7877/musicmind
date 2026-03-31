import { useState, useCallback } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getFullGraph, traverseGraph, submitFeedback, explodeGraph } from '../utils/api';
import GraphVisualization from '../components/GraphVisualization';
import NodeDetailPanel from '../components/NodeDetailPanel';
import ShareButton from '../components/ShareButton';
import type { GraphNode, SearchResponse } from '../types/api';

export default function GraphPage() {
  const { nodeId } = useParams<{ nodeId: string }>();
  const location = useLocation();
  const searchResult = (location.state as { searchResult?: SearchResponse })?.searchResult;

  const [depth, setDepth] = useState(2);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Fetch the full cumulative graph (all enriched songs)
  const fullGraphQuery = useQuery({
    queryKey: ['graph', 'full'],
    queryFn: getFullGraph,
    retry: 1,
    staleTime: 0,
    refetchOnMount: 'always',
  });

  // Fall back to single-node traversal if full graph is unavailable
  const singleGraphQuery = useQuery({
    queryKey: ['graph', nodeId, depth],
    queryFn: () => traverseGraph(nodeId!, depth, searchResult?.merged_data),
    enabled: !!nodeId && fullGraphQuery.isError,
    retry: 2,
  });

  const graphQuery = fullGraphQuery.isError ? singleGraphQuery : fullGraphQuery;

  const feedbackMutation = useMutation({
    mutationFn: submitFeedback,
  });

  const queryClient = useQueryClient();
  const explodeMutation = useMutation({
    mutationFn: explodeGraph,
    onSuccess: (data) => {
      console.log(`[EXPLODE] Added ${data.new_nodes_added} nodes, ${data.new_edges_added} edges`);
      // Refetch the full graph to show the new nodes
      queryClient.invalidateQueries({ queryKey: ['graph', 'full'] });
    },
  });

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
  }, []);

  const handleFeedback = useCallback(
    (feedbackType: string, value: number, comment?: string) => {
      if (!selectedNode) return;
      feedbackMutation.mutate({
        node_id: selectedNode.id,
        feedback_type: feedbackType,
        feedback_value: value,
        comment,
      });
    },
    [selectedNode, feedbackMutation],
  );

  return (
    <div className="h-[calc(100vh-10rem)] flex flex-col">
      {/* Top bar */}
      <div className="border-b border-mist/40 bg-cream/60 backdrop-blur-sm px-6 py-3 flex items-center justify-between animate-fade-in">
        <div className="flex items-center gap-4">
          {searchResult && (
            <div className="flex items-center gap-2">
              <span className="font-[family-name:var(--font-display)] text-lg text-ink">
                {(searchResult.merged_data?.title as string) || 'Song Graph'}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber/10 text-amber font-[family-name:var(--font-mono)] font-medium">
                {Math.round(searchResult.completeness_score * 100)}% complete
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <label htmlFor="depth" className="text-slate text-xs">
              Depth
            </label>
            <input
              id="depth"
              type="range"
              min={1}
              max={5}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="w-24 accent-amber"
            />
            <span className="font-[family-name:var(--font-mono)] text-xs text-amber w-4 text-center">
              {depth}
            </span>
          </div>

          <div className="w-px h-5 bg-mist" />

          {graphQuery.data && (
            <div className="flex items-center gap-3 text-xs text-ghost font-[family-name:var(--font-mono)]">
              <span>{graphQuery.data.total_nodes} nodes</span>
              <span>{graphQuery.data.total_edges} edges</span>
              {graphQuery.data.truncated && (
                <span className="text-amber">truncated</span>
              )}
            </div>
          )}

          <div className="w-px h-5 bg-mist" />

          <button
            onClick={() => explodeMutation.mutate()}
            disabled={explodeMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber/10 text-amber hover:bg-amber/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="Explode graph to enrich with more songs, albums, and artists"
          >
            {explodeMutation.isPending ? (
              <>
                <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span>Exploding...</span>
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                </svg>
                <span>Explode</span>
              </>
            )}
          </button>

          <ShareButton nodeId={nodeId || ''} />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 relative overflow-hidden">
        {graphQuery.isPending && (
          <div className="absolute inset-0 flex items-center justify-center bg-paper/80 z-10">
            <div className="flex flex-col items-center gap-4 animate-fade-up">
              <div className="relative">
                <div className="w-12 h-12 border-2 border-mist rounded-full" />
                <div className="absolute inset-0 w-12 h-12 border-2 border-amber border-t-transparent rounded-full animate-spin" />
              </div>
              <span className="text-sm text-slate">Traversing graph...</span>
            </div>
          </div>
        )}

        {graphQuery.isError && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center animate-fade-up">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-rust/10 flex items-center justify-center">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-rust">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <p className="text-slate mb-2">Failed to load graph</p>
              <button
                onClick={() => graphQuery.refetch()}
                className="text-sm font-semibold text-amber hover:text-rust transition-colors cursor-pointer"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {graphQuery.data && (
          <GraphVisualization
            nodes={graphQuery.data.nodes}
            edges={graphQuery.data.edges}
            onNodeClick={handleNodeClick}
            selectedNodeId={selectedNode?.id || nodeId}
          />
        )}

        {/* Node detail panel */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onFeedback={handleFeedback}
            feedbackPending={feedbackMutation.isPending}
            feedbackSuccess={feedbackMutation.isSuccess}
          />
        )}
      </div>

      {/* Legend */}
      <div className="border-t border-mist/40 bg-cream/60 backdrop-blur-sm px-6 py-2 flex items-center gap-4 text-xs">
        {[
          { type: 'Song', color: 'bg-node-song' },
          { type: 'Artist', color: 'bg-node-artist' },
          { type: 'Album', color: 'bg-node-album' },
          { type: 'Label', color: 'bg-node-label' },
          { type: 'Instrument', color: 'bg-node-instrument' },
          { type: 'Venue', color: 'bg-node-venue' },
          { type: 'Concert', color: 'bg-node-concert' },
        ].map((item) => (
          <div key={item.type} className="flex items-center gap-1.5">
            <div className={`w-2.5 h-2.5 rounded-full ${item.color}`} />
            <span className="text-slate">{item.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
