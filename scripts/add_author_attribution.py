"""Add author attribution to all new files.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from pathlib import Path

# All new files we created that need author attribution
new_files = [
    # LLM modules
    'berb/llm/output_limits.py',
    'berb/llm/structured_outputs.py',
    'berb/llm/prompt_cache.py',
    'berb/llm/batch_api.py',
    'berb/llm/model_cascade.py',
    'berb/llm/model_router.py',
    'berb/llm/speculative_gen.py',
    'berb/llm/speculative_router.py',
    'berb/llm/eval_dataset.py',
    'berb/llm/adaptive_temp.py',
    'berb/llm/nadirclaw_router.py',
    # Pipeline modules
    'berb/pipeline/tdd_generation.py',
    'berb/pipeline/diff_revisions.py',
    'berb/pipeline/dependency_context.py',
    # Utils
    'berb/utils/token_tracker.py',
    # Memory vault
    'berb/memory_vault/__init__.py',
]

author_line = '\n# Author: Georgios-Chrysovalantis Chatzivantsidis\n'

updated = 0
skipped = 0

for file_path in new_files:
    path = Path(file_path)
    if not path.exists():
        print(f'NOT FOUND: {file_path}')
        skipped += 1
        continue
    
    content = path.read_text(encoding='utf-8')
    
    # Check if author already present
    if 'Author: Georgios-Chrysovalantis Chatzivantsidis' in content:
        print(f'SKIPPED (author present): {file_path}')
        skipped += 1
        continue
    
    # Add author after opening docstring
    if content.startswith('"""'):
        end_docstring = content.find('"""', 3)
        if end_docstring > 0:
            insert_pos = content.find('\n', end_docstring)
            if insert_pos > 0:
                insert_pos += 1
                new_content = content[:insert_pos] + author_line + content[insert_pos:]
                path.write_text(new_content, encoding='utf-8')
                print(f'UPDATED: {file_path}')
                updated += 1
                continue
    
    print(f'SKIPPED (no docstring): {file_path}')
    skipped += 1

print(f'\nDone! Updated: {updated}, Skipped: {skipped}')
