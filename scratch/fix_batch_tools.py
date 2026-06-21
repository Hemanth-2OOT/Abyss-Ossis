import re

def fix_cli():
    with open('cli.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    out_lines = []
    i = 0
    in_parse_block = False
    
    while i < len(lines):
        line = lines[i]
        
        # 1. Fix retrieval inefficiency
        if 'auto_context = search_index(session, user_input)' in line:
            indent = line[:len(line) - len(line.lstrip())]
            out_lines.append(indent + 'auto_context = []\n')
            out_lines.append(indent + 'if task.get("needs_retrieval", True):\n')
            out_lines.append(indent + '    auto_context = search_index(session, user_input)\n')
            i += 1
            continue
            
        if 'if auto_context:' in line and 'full_context = build_context(auto_context)' in lines[i+1]:
            # Indent the next two lines as well, but wait, if task.get("needs_retrieval", True): encompasses auto_context check.
            # It's easier to just do:
            pass # We'll just leave 'if auto_context:' alone, as auto_context is empty if skipped.
            
        # 2. Batch tool execution
        if 'if parsed_response and isinstance(parsed_response, dict):' in line:
            indent = line[:len(line) - len(line.lstrip())]
            out_lines.append(indent + 'if parsed_response:\n')
            out_lines.append(indent + '    parsed_responses = parsed_response if isinstance(parsed_response, list) else [parsed_response]\n')
            out_lines.append(indent + '    has_tool_call = any(isinstance(pr, dict) and pr.get("type") == "tool_call" for pr in parsed_responses)\n')
            out_lines.append(indent + '    if has_tool_call:\n')
            out_lines.append(indent + '        worker_history.append({"role": "assistant", "content": raw_response})\n')
            out_lines.append(indent + '    batch_results = []\n')
            out_lines.append(indent + '    any_failed = False\n')
            out_lines.append(indent + '    for pr in parsed_responses:\n')
            out_lines.append(indent + '        if not isinstance(pr, dict): continue\n')
            out_lines.append(indent + '        parsed_response = pr\n')
            out_lines.append(indent + '        resp_type = parsed_response.get("type")\n\n')
            out_lines.append(indent + '        if resp_type == "tool_call" and tool_loops < max_tool_loops:\n')
            i += 1
            
            # Skip the old 'resp_type = parsed_response.get("type")' and 'if resp_type == "tool_call"...'
            while 'resp_type = parsed_response.get("type")' in lines[i] or 'if resp_type == "tool_call"' in lines[i]:
                i += 1
                
            in_parse_block = True
            continue
            
        if in_parse_block:
            if 'worker_history.append({"role": "assistant", "content": raw_response})' in line:
                i += 1
                continue
            if 'worker_history.append({' in line and '"role": "user"' in lines[i+1] and 'TOOL RESULT:' in lines[i+2]:
                # Collect tool result to batch_results
                indent = line[:len(line) - len(line.lstrip())]
                out_lines.append(indent + 'batch_results.append(f"TOOL: {tool_name}\\nRESULT:\\n{combined_result_str}")\n')
                out_lines.append(indent + 'if not tool_result_dict["success"]:\n')
                out_lines.append(indent + '    any_failed = True\n')
                # Skip the append lines
                while '})' not in lines[i]:
                    i += 1
                i += 1
                continue
            if 'if not tool_result_dict["success"]:' in line and 'worker_history.append({' in lines[i+1] and 'The previous tool call failed' in lines[i+3]:
                # Skip this block as we handle it at the end of the batch
                while '})' not in lines[i]:
                    i += 1
                i += 1
                continue
            if 'tool_loops += 1' in line and 'metrics.record_retry()' in lines[i+1] and 'continue' in lines[i+2]:
                # Reached the end of the tool execution block
                indent = line[:len(line) - len(line.lstrip())]
                i += 3
                continue
            if 'elif resp_type == "response":' in line:
                indent = line[:len(line) - len(line.lstrip())]
                out_lines.append(indent[:-4] + '    if batch_results:\n')
                out_lines.append(indent[:-4] + '        worker_history.append({"role": "user", "content": "\\n\\n".join(batch_results) + "\\n\\nCRITICAL INSTRUCTION: Output ONLY valid JSON starting with \'{\'. No prose outside JSON."})\n')
                out_lines.append(indent[:-4] + '        if any_failed:\n')
                out_lines.append(indent[:-4] + '            worker_history.append({"role": "user", "content": "Some tool calls failed. Correct and retry. DO NOT APOLOGIZE."})\n')
                out_lines.append(indent[:-4] + '        tool_loops += 1\n')
                out_lines.append(indent[:-4] + '        metrics.record_retry()\n')
                out_lines.append(indent[:-4] + '        continue\n\n')
                out_lines.append(indent[:-4] + '    if any(pr.get("type") == "response" for pr in parsed_responses):\n')
                i += 1
                while 'response_content = ' not in lines[i]: i += 1
                out_lines.append(indent[:-4] + '        response_content = " ".join([pr.get("content", "") for pr in parsed_responses if pr.get("type") == "response"]) or raw_response\n')
                i += 1
                in_parse_block = False
                continue
            
            # Indent by 4 spaces
            out_lines.append("    " + line)
            i += 1
        else:
            out_lines.append(line)
            i += 1
            
    with open('cli.py', 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

if __name__ == "__main__":
    fix_cli()
