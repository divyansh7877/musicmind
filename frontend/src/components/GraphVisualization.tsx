import { useRef, useEffect, useCallback, useState } from 'react';
import * as d3 from 'd3';
import type { GraphNode, GraphEdge } from '../types/api';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (node: GraphNode) => void;
  selectedNodeId?: string;
}

const NODE_COLORS: Record<string, string> = {
  Song: '#c2703e',
  Artist: '#8b3a1e',
  Album: '#6b7c5e',
  RecordLabel: '#7c6b5e',
  Instrument: '#5e6b7c',
  Venue: '#7c5e6b',
  Concert: '#5e7c6b',
};

const NODE_RADIUS: Record<string, number> = {
  Song: 18,
  Artist: 22,
  Album: 16,
  RecordLabel: 14,
  Instrument: 12,
  Venue: 14,
  Concert: 14,
};

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  type: string;
  data: Record<string, unknown>;
  label: string;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  edge_type: string;
}

function getLabel(node: GraphNode): string {
  const d = node.data;
  return (d.title || d.name || node.type) as string;
}

export default function GraphVisualization({ nodes, edges, onNodeClick, selectedNodeId }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: SimNode } | null>(null);

  const buildGraph = useCallback(() => {
    if (!svgRef.current || !containerRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const { width, height } = containerRef.current.getBoundingClientRect();

    const simNodes: SimNode[] = nodes.map((n) => ({
      id: n.id,
      type: n.type,
      data: n.data,
      label: getLabel(n),
    }));

    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));

    const simLinks: SimLink[] = edges
      .filter((e) => nodeMap.has(e.from_node_id) && nodeMap.has(e.to_node_id))
      .map((e) => ({
        source: e.from_node_id,
        target: e.to_node_id,
        edge_type: e.edge_type,
      }));

    const g = svg.append('g');

    // Zoom
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform);
      });
    svg.call(zoom);

    // Arrow markers
    const defs = svg.append('defs');
    Object.entries(NODE_COLORS).forEach(([type, color]) => {
      defs.append('marker')
        .attr('id', `arrow-${type}`)
        .attr('viewBox', '0 -4 8 8')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-4L8,0L0,4')
        .attr('fill', color)
        .attr('opacity', 0.4);
    });

    // Simulation
    const simulation = d3.forceSimulation(simNodes)
      .force('link', d3.forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d) => NODE_RADIUS[(d as SimNode).type] + 8));

    // Links
    const link = g.append('g')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(simLinks)
      .join('line')
      .attr('stroke', '#d4cfc5')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6);

    // Edge labels
    const edgeLabel = g.append('g')
      .selectAll<SVGTextElement, SimLink>('text')
      .data(simLinks)
      .join('text')
      .text((d) => d.edge_type.replace(/_/g, ' '))
      .attr('font-size', '8px')
      .attr('font-family', 'var(--font-mono)')
      .attr('fill', '#bfb9ad')
      .attr('text-anchor', 'middle')
      .attr('dy', -4);

    // Node groups
    const node = g.append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(simNodes)
      .join('g')
      .style('cursor', 'pointer')
      .call(
        d3.drag<SVGGElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    // Glow for selected
    node.append('circle')
      .attr('r', (d) => (NODE_RADIUS[d.type] || 14) + 6)
      .attr('fill', 'none')
      .attr('stroke', (d) => d.id === selectedNodeId ? NODE_COLORS[d.type] || '#c2703e' : 'none')
      .attr('stroke-width', 2)
      .attr('stroke-opacity', 0.3)
      .attr('class', 'selection-ring');

    // Node circles
    node.append('circle')
      .attr('r', (d) => NODE_RADIUS[d.type] || 14)
      .attr('fill', (d) => NODE_COLORS[d.type] || '#c2703e')
      .attr('stroke', '#f5f0e8')
      .attr('stroke-width', 2)
      .attr('opacity', 0.9);

    // Node icon text
    node.append('text')
      .text((d) => d.type.charAt(0))
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('font-family', 'var(--font-mono)')
      .attr('fill', '#faf7f0')
      .attr('pointer-events', 'none');

    // Labels
    node.append('text')
      .text((d) => d.label.length > 20 ? d.label.slice(0, 18) + '...' : d.label)
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => (NODE_RADIUS[d.type] || 14) + 14)
      .attr('font-size', '11px')
      .attr('font-family', 'var(--font-body)')
      .attr('fill', '#4a4a4a')
      .attr('pointer-events', 'none');

    // Events
    node.on('click', (_event, d) => {
      onNodeClick({ id: d.id, type: d.type, data: d.data });
    });

    node.on('mouseenter', (event, d) => {
      const rect = containerRef.current!.getBoundingClientRect();
      setTooltip({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top - 10,
        node: d,
      });
    });

    node.on('mouseleave', () => {
      setTooltip(null);
    });

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => (d.source as SimNode).x!)
        .attr('y1', (d) => (d.source as SimNode).y!)
        .attr('x2', (d) => (d.target as SimNode).x!)
        .attr('y2', (d) => (d.target as SimNode).y!);

      edgeLabel
        .attr('x', (d) => ((d.source as SimNode).x! + (d.target as SimNode).x!) / 2)
        .attr('y', (d) => ((d.source as SimNode).y! + (d.target as SimNode).y!) / 2);

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    // Initial zoom to fit
    setTimeout(() => {
      const bounds = (g.node() as SVGGElement)?.getBBox();
      if (bounds) {
        const dx = bounds.width + 100;
        const dy = bounds.height + 100;
        const x = bounds.x - 50;
        const y = bounds.y - 50;
        const scale = Math.min(0.9, Math.min(width / dx, height / dy));
        const translate: [number, number] = [
          width / 2 - scale * (x + dx / 2),
          height / 2 - scale * (y + dy / 2),
        ];
        svg.transition()
          .duration(750)
          .call(zoom.transform, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
      }
    }, 500);

    return () => { simulation.stop(); };
  }, [nodes, edges, onNodeClick, selectedNodeId]);

  useEffect(() => {
    const cleanup = buildGraph();
    return () => cleanup?.();
  }, [buildGraph]);

  return (
    <div ref={containerRef} className="w-full h-full relative bg-paper">
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ background: 'radial-gradient(circle at 50% 50%, var(--color-cream), var(--color-paper))' }}
      />
      {tooltip && (
        <div
          className="graph-tooltip animate-fade-in"
          style={{ left: tooltip.x + 12, top: tooltip.y - 20 }}
        >
          <div className="flex items-center gap-2 mb-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: NODE_COLORS[tooltip.node.type] }}
            />
            <span className="font-semibold text-ink text-xs">{tooltip.node.type}</span>
          </div>
          <p className="text-ink font-[family-name:var(--font-display)] text-sm">{tooltip.node.label}</p>
          {tooltip.node.data.completeness_score !== undefined && (
            <p className="text-ghost text-xs mt-1 font-[family-name:var(--font-mono)]">
              {Math.round((tooltip.node.data.completeness_score as number) * 100)}% complete
            </p>
          )}
        </div>
      )}
    </div>
  );
}
