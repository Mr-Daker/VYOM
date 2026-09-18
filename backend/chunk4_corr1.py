with open("app/services/gap_detection_service.py", "r") as f:
    content = f.read()

import re

# We need to rewrite `_get_direct_and_transitive`
new_dfs_method = """    def _get_direct_and_transitive(self, graph: Dict[UUID, List[UUID]], target_id: UUID, all_comps: Dict[UUID, object]) -> Tuple[List[UUID], List[UUID], List[str]]:
        direct = graph.get(target_id, [])
        # Deduplicate direct just in case
        direct_unique = []
        for d in direct:
            if d not in direct_unique:
                direct_unique.append(d)
        direct = direct_unique
        direct_set = set(direct)

        transitive = []
        warnings = []
        
        WHITE = 0
        GRAY = 1
        BLACK = 2
        
        colors = {}
        output_seen = set()

        def dfs(node, path):
            colors[node] = GRAY

            for neighbor in graph.get(node, []):
                if neighbor == target_id:
                    path_names = " -> ".join([all_comps[p].name for p in path] + [all_comps[target_id].name])
                    warnings.append(f"Cycle detected in prerequisite graph: {path_names}")
                    continue

                state = colors.get(neighbor, WHITE)
                
                if state == GRAY:
                    # To get the cycle portion of the path
                    cycle_start_idx = path.index(neighbor) if neighbor in path else 0
                    cycle_path = path[cycle_start_idx:]
                    path_names = " -> ".join([all_comps[p].name for p in cycle_path] + [all_comps[neighbor].name])
                    warnings.append(f"Cycle detected in prerequisite graph: {path_names}")
                    continue
                    
                if neighbor not in direct_set and neighbor not in output_seen:
                    output_seen.add(neighbor)
                    transitive.append(neighbor)
                    
                if state == WHITE:
                    dfs(neighbor, path + [neighbor])
                    
            colors[node] = BLACK

        # Target itself is considered BLACK for regular visitation if you wanted, 
        # but explicit `neighbor == target_id` check handles it cleanly.
        for d in direct:
            if colors.get(d, WHITE) == WHITE:
                dfs(d, [target_id, d])
                
        warnings = list(set(warnings))
        return direct, transitive, warnings"""

# Replace the old method
content = re.sub(
    r"    def _get_direct_and_transitive.*?return direct, transitive, warnings", 
    new_dfs_method, 
    content, 
    flags=re.DOTALL
)

# Fix historical confidence
content = content.replace("eff_conf = m.confidence", "eff_conf = m.confidence")
# Find the assignment of eff_last_updated for historical evidence and insert eff_conf
content = re.sub(
    r"elif e:\s+mastery_source = \"historical_evidence\"\s+eff_score = e.score",
    "elif e:\n                    mastery_source = \"historical_evidence\"\n                    eff_score = e.score\n                    eff_conf = getattr(e, 'confidence', None)",
    content
)
content = content.replace("eff_conf = getattr(e, 'confidence', None)", "eff_conf = getattr(e, 'confidence', None)") # already done

# Ensure `all_comps` is loaded before _get_direct_and_transitive
# In detect_gaps, all_comps is loaded after. We must move it before.
content = re.sub(
    r"graph = self._build_graph\(\)\n        direct_ids, transitive_ids, warnings = self._get_direct_and_transitive\(graph, session.target_competency_id\)",
    "graph = self._build_graph()\n        all_comps = {c.id: c for c in self.comp_repo.get_all()}\n        direct_ids, transitive_ids, warnings = self._get_direct_and_transitive(graph, session.target_competency_id, all_comps)",
    content
)
# Remove the old all_comps loading
content = re.sub(
    r"        all_comps = \{c.id: c for c in self.comp_repo.get_all\(\)\}\n",
    "",
    content, count=1 # Only first one after the replacement
)

with open("app/services/gap_detection_service.py", "w") as f:
    f.write(content)
