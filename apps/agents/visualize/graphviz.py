"""
Graphviz utilities for generating PNG diagrams from LangGraph structures.
"""
import subprocess
import tempfile
import os


def generate_png_with_graphviz(graph_structure, output_file):
    """Generate PNG using graphviz dot command.
    
    Args:
        graph_structure: LangGraph graph structure from get_graph()
        output_file: Path to output PNG file
        
    Raises:
        Exception: If graphviz dot command is not available
    """
    # Check if dot command is available
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise Exception("graphviz 'dot' command not found. Install with: sudo apt-get install graphviz")
    
    # Convert graph structure to dot format
    dot_content = graph_to_dot(graph_structure)
    
    # Write dot file temporarily
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
        dot_file = f.name
        f.write(dot_content)
    
    try:
        # Generate PNG using dot command
        subprocess.run(
            ['dot', '-Tpng', '-o', output_file, dot_file],
            check=True,
            capture_output=True
        )
    finally:
        # Clean up temp file
        try:
            os.unlink(dot_file)
        except:
            pass


def graph_to_dot(graph_structure):
    """Convert LangGraph structure to Graphviz DOT format.
    
    Args:
        graph_structure: LangGraph graph structure from get_graph()
        
    Returns:
        str: DOT format string
    """
    lines = ['digraph G {']
    lines.append('  rankdir=TB;')
    lines.append('  node [shape=box, style=rounded];')
    lines.append('')
    
    # Add nodes
    for node_id, node in graph_structure.nodes.items():
        # Clean node name for display
        if node_id == '__start__':
            lines.append(f'  "{node_id}" [label="START", shape=ellipse, style=filled, fillcolor=lightgreen];')
        elif node_id == '__end__':
            lines.append(f'  "{node_id}" [label="END", shape=ellipse, style=filled, fillcolor=lightpink];')
        else:
            # Format node name
            clean_name = node_id.replace('_', ' ').title()
            lines.append(f'  "{node_id}" [label="{clean_name}"];')
    
    lines.append('')
    
    # Add edges
    for edge in graph_structure.edges:
        source = edge.source if hasattr(edge, 'source') else edge[0]
        target = edge.target if hasattr(edge, 'target') else edge[1]
        
        # Check if it's a conditional edge (dashed)
        is_conditional = hasattr(edge, 'conditional') and edge.conditional
        style = 'dashed' if is_conditional else 'solid'
        
        lines.append(f'  "{source}" -> "{target}" [style={style}];')
    
    lines.append('}')
    return '\n'.join(lines)

