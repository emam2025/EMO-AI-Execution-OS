# Phase 3: AST Parsing System - Plan

## Goal
Enhance the AST parsing system to use tree-sitter for robust, multi-language parsing while maintaining backward compatibility with the existing fallback parsers.

## Changes to Make

1. **Tree-sitter Integration**:
   - Install tree-sitter grammars for Python, JavaScript, TypeScript, JSON, YAML, Markdown
   - Create a tree-sitter parser manager that loads and caches grammars
   - Implement tree-sitter based parsing for each supported language

2. **Parser Abstraction Layer Enhancement**:
   - Update the `LanguageParser` interface to support both tree-sitter and fallback methods
   - Create a `TreeSitterParser` base class that handles common tree-sitter operations
   - Implement specific parsers for each language using tree-sitter when available

3. **Symbol Extraction Improvements**:
   - Extract more detailed symbols: methods, properties, decorators, interfaces, types, enums, etc.
   - Extract more accurate signatures including type annotations (for TypeScript/Python)
   - Extract JSDoc and docstring comments attached to symbols
   - Track symbol locations with precise byte offsets for IDE integration

4. **Dependency Resolution Enhancements**:
   - Resolve relative imports to absolute file paths where possible
   - Track dynamic imports (though these cannot be fully resolved statically)
   - Distinguish between dependency types (import, export, require, etc.) more precisely

5. **Performance Optimization**:
   - Cache parsed tree-sitter trees for unchanged files
   - Incremental parsing when only parts of a file change (if supported by tree-sitter)
   - Batch database operations for better performance

## Technical Details

### Tree-sitter Setup
- We will use the `tree_sitter` Python package
- We will load grammars from pre-compiled `.so` files or compile them at runtime
- We will store grammars in `.ai/tree-sitter/` directory

### Parser Structure
```
Parsers/
├── base.py                 # Base parser classes
├── python.py               # Python-specific tree-sitter parser
├── javascript.js           # JavaScript-specific tree-sitter parser
├── typescript.js           # TypeScript-specific tree-sitter parser
├── json.py                 # JSON parser
├── yaml.py                 # YAML parser
└── markdown.py             # Markdown parser
```

However, to keep everything in Python, we will implement all parsers in Python files.

### Symbol Storage Enhancements
We will extend the `symbols` table to include:
- `symbol_subtype`: More specific symbol type (method, property, etc.)
- `return_type`: For functions/methods
- `properties`: For classes/objects (JSON blob)
- `decorators`: List of decorators
- `type_parameters`: For generics

We will also enhance the `symbol_relationships` table with more relationship types.

## Integration Plan
1. Update the `get_parser_for_extension` function to return tree-sitter parsers when available
2. Keep fallback parsers for when tree-sitter is not available or fails
3. Update the indexing pipeline to use the new parsers
4. Add migration scripts to update the database schema for new symbol fields

## Risks and Tradeoffs
- **Complexity**: Tree-sitter adds complexity but provides much better accuracy
- **Dependencies**: Requires maintaining grammar files
- **Performance**: Tree-sitter is fast but adds memory overhead for storing parse trees
- **Compatibility**: We must ensure backward compatibility with existing indices

## Next Steps
Upon approval, we will:
1. Install tree-sitter and download grammars
2. Create the enhanced parser system
3. Update the database schema for enhanced symbol storage
4. Modify the indexer to use the new parsers
5. Test with the existing codebase

Please approve or provide feedback on this plan before we proceed with implementation.