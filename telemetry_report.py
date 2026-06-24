import json
import os
from collections import Counter

def main():
    log_file = os.path.join("logs", "telemetry.jsonl")
    if not os.path.exists(log_file):
        print("No telemetry data found at logs/telemetry.jsonl")
        return
        
    total_tasks = 0
    total_time = 0.0
    total_tools = 0
    total_passes = 0
    
    outcomes = Counter()
    model_stats = {}
    
    req_types = Counter()
    req_failures = Counter()
    
    with open(log_file, "r") as f:
        for line in f:
            if not line.strip(): continue
            try:
                record = json.loads(line)
                total_tasks += 1
                total_time += record.get("execution_time_seconds", 0)
                total_tools += record.get("total_tool_calls", 0)
                total_passes += record.get("total_reasoning_passes", 0)
                
                outcomes[record.get("failure_category", "UNKNOWN")] += 1
                
                worker_model = record.get("models", {}).get("worker", "unknown")
                if worker_model not in model_stats:
                    model_stats[worker_model] = {"total": 0, "success": 0, "validation_error": 0}
                model_stats[worker_model]["total"] += 1
                
                cat = record.get("failure_category")
                if cat == "SUCCESS":
                    model_stats[worker_model]["success"] += 1
                elif cat == "VALIDATION_ERROR":
                    model_stats[worker_model]["validation_error"] += 1
                    
                for req in record.get("requirements", []):
                    req_types[req["type"]] += 1
                    if req["status"] != "SATISFIED":
                        req_failures[req["type"]] += 1
            except Exception as e:
                pass
                
    if total_tasks == 0:
        print("No valid telemetry records found.")
        return
        
    avg_time = total_time / total_tasks
    avg_tools = total_tools / total_tasks
    avg_passes = total_passes / total_tasks
    
    print("=" * 40)
    print("=== Agent Telemetry Aggregate Report ===")
    print("=" * 40)
    print(f"Total Tasks Executed: {total_tasks}")
    print(f"Average Task Duration: {avg_time:.1f}s")
    print(f"Average Tool Calls: {avg_tools:.1f}")
    print(f"Average Reasoning Passes: {avg_passes:.1f}")
    print("\n--- Failure Categories ---")
    for cat, count in outcomes.most_common():
        print(f"  {cat:<20}: {count} ({count/total_tasks*100:.1f}%)")
        
    print("\n--- Requirement Reliability ---")
    for r_type, count in req_types.most_common():
        fails = req_failures[r_type]
        fail_rate = (fails / count) * 100 if count > 0 else 0
        print(f"  {r_type:<15}: {count} total, {fail_rate:.1f}% failure rate")
        
    print("\n--- Model Performance ---")
    for model, stats in model_stats.items():
        total = stats["total"]
        succ_rate = (stats["success"] / total) * 100 if total > 0 else 0
        val_rate = (stats["validation_error"] / total) * 100 if total > 0 else 0
        print(f"  {model:<15}: {total} tasks, {succ_rate:.1f}% success, {val_rate:.1f}% validation errs")
        
    print("=" * 40)

if __name__ == "__main__":
    main()
