import sys

def apply_batch():
    with open('cli.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 1. Retrieval bypass
        if "auto_context = search_index(session, user_input)" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out.append(indent + "auto_context = []\n")
            out.append(indent + "if task.get('needs_retrieval', True):\n")
            out.append(indent + "    auto_context = search_index(session, user_input)\n")
            i += 1
            continue
            
        # 2. Batch tool execution
        if "if parsed_response and isinstance(parsed_response, dict):" in line:
            indent = line[:len(line) - len(line.lstrip())]
            out.append(indent + "if parsed_response:\n")
            out.append(indent + "    parsed_responses = parsed_response if isinstance(parsed_response, list) else [parsed_response]\n")
            out.append(indent + "    has_tool_call = any(isinstance(pr, dict) and pr.get('type') == 'tool_call' for pr in parsed_responses)\n")
            out.append(indent + "    if has_tool_call:\n")
            out.append(indent + "        worker_history.append({'role': 'assistant', 'content': raw_response})\n")
            out.append(indent + "    batch_results = []\n")
            out.append(indent + "    any_failed = False\n")
            
            # Start loop
            out.append(indent + "    for pr in parsed_responses:\n")
            out.append(indent + "        if not isinstance(pr, dict): continue\n")
            out.append(indent + "        parsed_response = pr\n")
            out.append(indent + "        resp_type = parsed_response.get('type')\n\n")
            
            i += 1
            
            # Skip 'resp_type = parsed_response.get("type")' if present
            while "resp_type = parsed_response.get" in lines[i]: i += 1
            
            # Now we are at 'if resp_type == "tool_call" and tool_loops < max_tool_loops:'
            # We want to indent everything under this block until 'worker_history.append({"role": "assistant"'
            while True:
                curr = lines[i]
                if 'worker_history.append({"role": "assistant"' in curr:
                    break
                out.append("    " + curr if curr.strip() else curr)
                i += 1
                
            # Now at 'worker_history.append({"role": "assistant"'
            # We skip until 'tool_loops += 1'
            while 'tool_loops += 1' not in lines[i]:
                # But wait, collect result!
                # Actually, right here we want to append the tool result to batch_results!
                pass
                i += 1
                
            # We insert the batch collection logic right here (inside the for loop):
            tool_indent = indent + "        "
            out.append(tool_indent + "batch_results.append(f'TOOL RESULT:\\n{combined_result_str}')\n")
            out.append(tool_indent + "if not tool_result_dict['success']:\n")
            out.append(tool_indent + "    any_failed = True\n")
            
            # Skip 'tool_loops += 1', 'metrics.record_retry()', 'continue'
            while 'continue' not in lines[i]: i += 1
            i += 1 # skip continue
            
            # Now handle the post-for-loop logic (appending the batched user message)
            out.append("\n" + indent + "    if batch_results:\n")
            out.append(indent + "        worker_history.append({\n")
            out.append(indent + "            'role': 'user',\n")
            out.append(indent + "            'content': '\\n\\n'.join(batch_results) + '\\n\\nCRITICAL INSTRUCTION: When calling a tool, output ONLY valid JSON starting with \\'{\\' or \\'[{\\'. Do NOT explain.'\n")
            out.append(indent + "        })\n")
            out.append(indent + "        if any_failed:\n")
            out.append(indent + "            worker_history.append({'role': 'user', 'content': 'Some tool calls failed. Correct and retry.'})\n")
            out.append(indent + "        tool_loops += 1\n")
            out.append(indent + "        metrics.record_retry()\n")
            out.append(indent + "        continue\n\n")
            
            # Now handle 'elif resp_type == "response":'
            # Wait, the LLM might emit a list where the LAST item is a response?
            # Usually we just parse it out.
            out.append(indent + "    response_items = [pr for pr in parsed_responses if isinstance(pr, dict) and pr.get('type') == 'response']\n")
            out.append(indent + "    if response_items:\n")
            out.append(indent + "        response_content = ' '.join(pr.get('content', '') for pr in response_items)\n")
            out.append(indent + "        console.print() \n")
            out.append(indent + "        console.print(response_content, style='green', markup=False, highlight=False)\n")
            out.append(indent + "        worker_history.append({'role': 'assistant', 'content': response_content})\n")
            
            # Skip the old 'elif resp_type == "response":' block
            while 'if not response_content or not response_content.strip():' not in lines[i]:
                i += 1
                
            continue
            
        out.append(line)
        i += 1
        
    with open('cli.py', 'w', encoding='utf-8') as f:
        f.writelines(out)

if __name__ == '__main__':
    apply_batch()
