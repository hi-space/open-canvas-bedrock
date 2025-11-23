#!/usr/bin/env python3
"""
Generate a visual diagram of the Open Canvas LangGraph.
"""
import sys
import os

# Add the agents directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from open_canvas.graph import graph
    
    # Try to get the graph structure
    try:
        # LangGraph has a get_graph() method
        graph_structure = graph.get_graph()
        print("Graph structure retrieved successfully!")
        print(f"Graph name: {graph.name}")
        print(f"Nodes: {list(graph_structure.nodes.keys())}")
        print(f"Edges: {len(graph_structure.edges)} edges")
        
        # Try to print ASCII diagram
        try:
            from langgraph.graph import draw_ascii
            print("\n" + "="*80)
            print("ASCII Graph Diagram:")
            print("="*80)
            print(draw_ascii(graph_structure))
        except ImportError:
            print("\nNote: draw_ascii not available in this version of LangGraph")
        except Exception as e:
            print(f"\nCould not generate ASCII diagram: {e}")
            
    except AttributeError:
        print("Graph structure not available via get_graph()")
        print("Graph name:", getattr(graph, 'name', 'Unknown'))
        
except Exception as e:
    print(f"Error importing graph: {e}")
    import traceback
    traceback.print_exc()

