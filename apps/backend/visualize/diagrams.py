"""
Diagram generation utilities for LangGraph graphs.
"""
import os
import sys
from typing import Optional
from visualize.graphviz import generate_png_with_graphviz


def generate_diagram_for_graph(
    graph,
    graph_name: str,
    output_dir: str,
    print_ascii: bool = False,
    generate_png: bool = True
) -> tuple[Optional[str], Optional[str]]:
    """Generate Mermaid and PNG diagrams for a LangGraph.
    
    Args:
        graph: Compiled LangGraph instance
        graph_name: Name of the graph (used for output filenames)
        output_dir: Directory to save output files
        print_ascii: Whether to print ASCII diagram (requires grandalf)
        generate_png: Whether to generate PNG diagram
        
    Returns:
        tuple: (mermaid_file_path, png_file_path) or (None, None) on error
    """
    try:
        # Get the graph structure
        graph_structure = graph.get_graph()
        
        print(f"\n{'='*80}")
        print(f"Graph: {graph.name}")
        print(f"Nodes: {len(graph_structure.nodes)}")
        print(f"Edges: {len(graph_structure.edges)}")
        print(f"{'='*80}")
        
        # Generate ASCII diagram (optional)
        if print_ascii:
            try:
                print("\nASCII Diagram:")
                print("-" * 80)
                graph_structure.print_ascii()
            except ImportError:
                print("\nNote: ASCII diagram requires 'grandalf' package.")
        
        # Generate Mermaid diagram
        mermaid_code = graph_structure.draw_mermaid()
        
        # Save Mermaid to file
        mermaid_file = os.path.join(output_dir, f'{graph_name}_diagram.mmd')
        with open(mermaid_file, 'w') as f:
            f.write(mermaid_code)
        print(f"Mermaid diagram saved to: {mermaid_file}")
        
        png_file = None
        
        # Generate PNG if requested
        if generate_png:
            try:
                png_file = os.path.join(output_dir, f'{graph_name}_diagram.png')
                
                # First try LangGraph's built-in draw_png (uses pygraphviz)
                try:
                    graph_structure.draw_png(png_file)
                    print(f"PNG diagram saved to: {png_file}")
                except Exception:
                    # Fallback to graphviz dot command
                    print("Trying graphviz dot command as fallback...")
                    generate_png_with_graphviz(graph_structure, png_file)
                    print(f"PNG diagram saved to: {png_file}")
            except Exception as e:
                print(f"Note: PNG generation skipped ({e})")
        
        return (mermaid_file, png_file)
        
    except Exception as e:
        print(f"Error generating diagram for {graph_name}: {e}")
        import traceback
        traceback.print_exc()
        return (None, None)

