#!/usr/bin/env python3
"""
Generate diagrams for LangGraph graphs in the Open Canvas project.

Usage:
    # Generate all graphs
    python3 generate_diagrams.py
    
    # Generate specific graph
    python3 generate_diagrams.py open_canvas
    python3 generate_diagrams.py reflection
"""
import sys
import os

# Add the agents directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from visualize.diagrams import generate_diagram_for_graph


def load_graph(graph_name: str):
    """Load a graph module by name."""
    import importlib.util
    
    base_dir = os.path.dirname(__file__)
    graph_path = os.path.join(base_dir, graph_name, "graph.py")
    
    if not os.path.exists(graph_path):
        raise FileNotFoundError(f"Graph not found: {graph_path}")
    
    spec = importlib.util.spec_from_file_location(graph_name, graph_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    return module.graph


def main():
    """Generate diagrams for graphs."""
    base_dir = os.path.dirname(__file__)
    
    # All available graphs
    all_graphs = {
        "open_canvas": {
            "path": os.path.join(base_dir, "open_canvas", "graph.py"),
            "output_dir": os.path.join(base_dir, "open_canvas"),
        },
        "reflection": {
            "path": os.path.join(base_dir, "reflection", "graph.py"),
            "output_dir": os.path.join(base_dir, "reflection"),
        },
        "web_search": {
            "path": os.path.join(base_dir, "web_search", "graph.py"),
            "output_dir": os.path.join(base_dir, "web_search"),
        },
        "summarizer": {
            "path": os.path.join(base_dir, "summarizer", "graph.py"),
            "output_dir": os.path.join(base_dir, "summarizer"),
        },
        "thread_title": {
            "path": os.path.join(base_dir, "thread_title", "graph.py"),
            "output_dir": os.path.join(base_dir, "thread_title"),
        },
    }
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        # Generate specific graph(s)
        graph_names = sys.argv[1:]
        invalid = [name for name in graph_names if name not in all_graphs]
        if invalid:
            print(f"Error: Unknown graph(s): {', '.join(invalid)}")
            print(f"Available graphs: {', '.join(all_graphs.keys())}")
            sys.exit(1)
        graphs_to_generate = {name: all_graphs[name] for name in graph_names}
    else:
        # Generate all graphs
        graphs_to_generate = all_graphs
    
    print("="*80)
    print("Generating diagrams for Open Canvas graphs")
    print("="*80)
    
    results = []
    for graph_name, graph_info in graphs_to_generate.items():
        try:
            graph = load_graph(graph_name)
            mermaid_file, png_file = generate_diagram_for_graph(
                graph,
                graph_name,
                graph_info["output_dir"],
                print_ascii=False,
                generate_png=True
            )
            success = mermaid_file is not None
            results.append((graph_name, success))
        except Exception as e:
            print(f"Error loading graph {graph_name}: {e}")
            results.append((graph_name, False))
    
    print("\n" + "="*80)
    print("Summary:")
    print("="*80)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")
    
    print("\nAll diagrams generated!")


if __name__ == "__main__":
    main()

