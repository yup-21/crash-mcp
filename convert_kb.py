
import os
import yaml
import glob

def convert_methods_to_markdown(methods_dir, output_file):
    """Convert all YAML methods in a directory to a single Markdown file for Dify."""
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Write header
        outfile.write("# Linux Kernel Crash Analysis Methods\n\n")
        outfile.write("此文档包含了分析 Linux Kernel Crash 的标准方法和步骤。\n\n")
        
        yaml_files = glob.glob(os.path.join(methods_dir, "*.yaml"))
        yaml_files.sort()
        
        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                # Format as a Dify knowledge segment
                outfile.write("---\n\n") # Dify segment separator (optional but good for chunking)
                
                # Title
                outfile.write(f"## 方法: {data.get('name', 'Unknown')}\n\n")
                
                # Description
                desc = data.get('description', '').replace('\n', ' ')
                outfile.write(f"**描述**: {desc}\n\n")
                
                # Triggers (Keywords)
                triggers = [t.get('pattern') for t in data.get('triggers', []) if 'pattern' in t]
                if triggers:
                    outfile.write(f"**适用场景/关键词**: {', '.join(triggers)}\n\n")
                
                # Steps
                outfile.write("**分析步骤**:\n")
                steps = data.get('steps', [])
                for step in steps:
                    order = step.get('order', 0)
                    purpose = step.get('purpose', '')
                    command = step.get('command', '')
                    outfile.write(f"{order}. **{purpose}**\n")
                    outfile.write(f"   - 命令: `{command}`\n")
                
                outfile.write("\n")
                
                # Outputs
                outputs = data.get('outputs', [])
                if outputs:
                    outfile.write("**关键指标**:\n")
                    for out in outputs:
                        outfile.write(f"- {out.get('name')} ({out.get('type')})\n")
                
                outfile.write("\n")
                
            except Exception as e:
                print(f"Error processing {yaml_file}: {e}")

    print(f"Successfully converted {len(yaml_files)} methods to {output_file}")

if __name__ == "__main__":
    METHODS_DIR = "knowledge/methods"
    OUTPUT_FILE = "dify_knowledge_import.md"
    convert_methods_to_markdown(METHODS_DIR, OUTPUT_FILE)
