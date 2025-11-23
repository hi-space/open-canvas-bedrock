#!/usr/bin/env python3
"""
Generate a visual diagram of the Open Canvas LangGraph using matplotlib and networkx.
"""
import sys
import os

# Add the agents directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from open_canvas.graph import graph
    
    # Get the graph structure
    graph_structure = graph.get_graph()
    
    # Create a NetworkX graph for visualization
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        
        # Create directed graph
        G = nx.DiGraph()
        
        # Add nodes
        node_colors = {}
        node_labels = {}
        
        # Define node categories and colors
        entry_nodes = ['__start__', 'generatePath']
        artifact_nodes = ['generateArtifact', 'rewriteArtifact', 'updateArtifact', 
                         'updateHighlightedText', 'rewriteArtifactTheme', 
                         'rewriteCodeArtifactTheme']
        special_nodes = ['webSearch', 'routePostWebSearch', 'customAction', 
                        'replyToGeneralInput']
        postprocess_nodes = ['generateFollowup', 'reflect', 'cleanState', 
                            'generateTitle', 'summarizer']
        end_nodes = ['__end__']
        
        # Add all nodes
        for node in graph_structure.nodes.keys():
            G.add_node(node)
            if node in entry_nodes:
                node_colors[node] = '#90EE90'  # Light green
            elif node in artifact_nodes:
                node_colors[node] = '#FFD700'  # Gold
            elif node in special_nodes:
                node_colors[node] = '#98FB98'  # Pale green
            elif node in postprocess_nodes:
                node_colors[node] = '#DDA0DD'  # Plum
            elif node in end_nodes:
                node_colors[node] = '#FFB6C1'  # Light pink
            else:
                node_colors[node] = '#87CEEB'  # Sky blue
            
            # Create labels (remove __start__ and __end__)
            if node == '__start__':
                node_labels[node] = 'START'
            elif node == '__end__':
                node_labels[node] = 'END'
            else:
                # Format node name for display
                label = node.replace('_', ' ').title()
                node_labels[node] = label
        
        # Add edges
        for edge in graph_structure.edges:
            source = edge.source if hasattr(edge, 'source') else edge[0]
            target = edge.target if hasattr(edge, 'target') else edge[1]
            G.add_edge(source, target)
        
        # Create figure
        plt.figure(figsize=(20, 14))
        
        # Use hierarchical layout
        pos = nx.spring_layout(G, k=2, iterations=50, seed=42)
        
        # Adjust positions for better layout
        # Move START to top left
        if '__start__' in pos:
            pos['__start__'] = (-2, 1)
        if 'generatePath' in pos:
            pos['generatePath'] = (0, 1)
        
        # Move artifact nodes to left
        artifact_x = -1.5
        artifact_y_start = 0.5
        for i, node in enumerate(artifact_nodes):
            if node in pos:
                pos[node] = (artifact_x, artifact_y_start - i * 0.4)
        
        # Move special nodes to center-left
        special_x = 0
        special_y_start = 0.5
        for i, node in enumerate(special_nodes):
            if node in pos:
                pos[node] = (special_x, special_y_start - i * 0.4)
        
        # Move postprocess nodes to right
        postprocess_x = 1.5
        postprocess_y_start = 0.5
        for i, node in enumerate(postprocess_nodes):
            if node in pos:
                pos[node] = (postprocess_x, postprocess_y_start - i * 0.4)
        
        # Move END to top right
        if '__end__' in pos:
            pos['__end__'] = (2, 1)
        
        # Draw nodes
        node_color_list = [node_colors.get(node, '#87CEEB') for node in G.nodes()]
        nx.draw_networkx_nodes(G, pos, node_color=node_color_list, 
                              node_size=3000, alpha=0.9, node_shape='s')
        
        # Draw edges
        nx.draw_networkx_edges(G, pos, edge_color='gray', arrows=True, 
                              arrowsize=20, alpha=0.6, width=1.5,
                              connectionstyle='arc3,rad=0.1')
        
        # Draw labels
        nx.draw_networkx_labels(G, pos, node_labels, font_size=8, font_weight='bold')
        
        # Create legend
        legend_elements = [
            mpatches.Patch(color='#90EE90', label='Entry Point'),
            mpatches.Patch(color='#FFD700', label='Artifact Operations'),
            mpatches.Patch(color='#98FB98', label='Special Functions'),
            mpatches.Patch(color='#DDA0DD', label='Post-processing'),
            mpatches.Patch(color='#FFB6C1', label='End Point'),
            mpatches.Patch(color='#87CEEB', label='Other'),
        ]
        plt.legend(handles=legend_elements, loc='upper right', fontsize=10)
        
        plt.title('Open Canvas LangGraph Structure', fontsize=16, fontweight='bold', pad=20)
        plt.axis('off')
        plt.tight_layout()
        
        # Save figure
        output_path = os.path.join(os.path.dirname(__file__), 'graph_diagram.png')
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"Graph diagram saved to: {output_path}")
        
        # Also save as SVG for better quality
        output_path_svg = os.path.join(os.path.dirname(__file__), 'graph_diagram.svg')
        plt.savefig(output_path_svg, format='svg', bbox_inches='tight', facecolor='white')
        print(f"Graph diagram (SVG) saved to: {output_path_svg}")
        
    except ImportError as e:
        print(f"Required libraries not available: {e}")
        print("Please install: pip install matplotlib networkx")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating visualization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
except Exception as e:
    print(f"Error importing graph: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

