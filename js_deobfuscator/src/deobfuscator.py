import esprima
import jsbeautifier
import escodegen
import re
from collections import Counter
from py_mini_racer import MiniRacer

# --- AST traversal base classes ---
class AstVisitor:
    def visit(self, node):
        if node is None: return
        if isinstance(node, list):
            for item in node: self.visit(item)
            return
        if not hasattr(node, 'type') or node.type is None: return
        for field in dir(node):
            if not (field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']):
                value = getattr(node, field)
                if hasattr(value, 'type'): setattr(value, 'parent', node)
                elif isinstance(value, list):
                    for child in value:
                        if hasattr(child, 'type'): setattr(child, 'parent', node)
        method_name = 'visit_' + node.type
        visitor = getattr(self, method_name, self.generic_visit)
        visitor(node)
    def generic_visit(self, node):
        for field in dir(node):
            if field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']: continue
            value = getattr(node, field)
            if value is None: continue
            self.visit(value)

class AstTransformer(AstVisitor):
    def visit(self, node):
        if node is None: return None
        if isinstance(node, list):
            new_list = []
            for item in node:
                new_item = self.visit(item)
                if new_item is not None:
                    if isinstance(new_item, list): new_list.extend(new_item)
                    else: new_list.append(new_item)
            return new_list
        if not hasattr(node, 'type') or node.type is None: return node
        for field in dir(node):
            if not (field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']):
                value = getattr(node, field)
                if hasattr(value, 'type'): setattr(value, 'parent', node)
                elif isinstance(value, list):
                    for child in value:
                        if hasattr(child, 'type'): setattr(child, 'parent', node)
        method_name = 'visit_' + node.type
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)
    def generic_visit(self, node):
        for field in dir(node):
            if field.startswith('_') or callable(getattr(node, field)) or field in ['type', 'loc', 'range', 'parent']: continue
            old_value = getattr(node, field)
            if old_value is None: continue
            new_value = self.visit(old_value)
            setattr(node, field, new_value)
        return node

# --- Deobfuscation Passes ---

class ContextualResolver(AstTransformer):
    """
    This resolver is the core of the solution. It creates a JS context,
    loads all the functions, and then smartly calls the main wrapper
    to initialize the nested decoders before attempting to resolve calls.
    """
    def __init__(self, ast):
        self.js_ctx = None
        self.function_names = set()
        self._initialize_context(ast)

    def _initialize_context(self, ast):
        if not ast.body:
            self.js_ctx = None
            return

        # 1. Get all top-level function names
        for node in ast.body:
            if node.type == 'FunctionDeclaration':
                self.function_names.add(node.id.name)

        # 2. Create the context by executing the script minus the final call
        original_last_statement = ast.body.pop()
        context_code = escodegen.generate(ast)
        ast.body.append(original_last_statement) # Restore AST for later passes

        # 3. Get the name of the main wrapper function from the final call
        main_wrapper_name = None
        if (original_last_statement.type == 'ExpressionStatement' and
            original_last_statement.expression.type == 'CallExpression' and
            original_last_statement.expression.callee.type == 'Identifier'):
            main_wrapper_name = original_last_statement.expression.callee.name

        try:
            self.js_ctx = MiniRacer()
            self.js_ctx.eval("var console = {log: function(){}};")
            self.js_ctx.eval(context_code)

            # 4. **CRITICAL STEP**: Call the main wrapper with no args.
            # This triggers the `if (!var) { var = function... }` blocks,
            # defining the nested decoders inside the JS context.
            if main_wrapper_name:
                self.js_ctx.eval(f"{main_wrapper_name}()")
                self.function_names.add(main_wrapper_name)

            print("Successfully initialized and primed JavaScript context.")
        except Exception as e:
            print(f"Error initializing context: {e}")
            self.js_ctx = None

    def visit_CallExpression(self, node):
        node = self.generic_visit(node)
        if not self.js_ctx: return node

        # Check if we are inside a function declaration, if so, don't resolve
        parent = getattr(node, 'parent', None)
        in_func_decl = False
        while parent:
            if parent.type == 'FunctionDeclaration':
                in_func_decl = True
                break
            parent = getattr(parent, 'parent', None)

        if in_func_decl:
            return node

        if node.callee.type == 'Identifier':
            # Use a broader check: if the function exists in the context, try to resolve it.
            # This is safe because we primed the context with the nested functions.
            try:
                if self.js_ctx.eval(f"typeof {node.callee.name} === 'function'"):
                    # Don't replace the final top-level call itself
                    parent = getattr(node, 'parent', None)
                    if parent and parent.type == 'ExpressionStatement':
                        return node

                    call_code = escodegen.generate(node)
                    result = self.js_ctx.eval(call_code)
                    if isinstance(result, (str, int, float, bool)):
                        print(f"Resolved call '{call_code}' to literal: {result}")
                        return esprima.nodes.Literal(value=result, raw=repr(result))
            except Exception:
                pass
        return node

    def visit_MemberExpression(self, node):
        node = self.generic_visit(node)
        if self.js_ctx and node.computed and getattr(node.property, 'type', '') == 'CallExpression':
            try:
                prop_call_code = escodegen.generate(node.property)
                result = self.js_ctx.eval(prop_call_code)
                if isinstance(result, str):
                    print(f"Resolved member access '{prop_call_code}' to literal: {result}")
                    node.computed = False
                    node.property = esprima.nodes.Identifier(name=result)
            except Exception:
                pass
        return node

class ExpressionSimplifier(AstTransformer):
    def __init__(self):
        self.simplified_count = 0
    def visit_BinaryExpression(self, node):
        node = self.generic_visit(node)
        if getattr(node.left, 'type', '') == 'Literal' and getattr(node.right, 'type', '') == 'Literal':
            if node.operator == '+' and isinstance(node.left.value, str) and isinstance(node.right.value, str):
                result = node.left.value + node.right.value
                self.simplified_count += 1
                return esprima.nodes.Literal(value=result, raw=repr(result))
        return node

class FinalCleanup(AstTransformer):
    def visit_VariableDeclaration(self, node):
        # Remove the huge, now-unused string array
        if (len(node.declarations) == 1 and
            getattr(node.declarations[0].init, 'type', '') == 'ArrayExpression' and
            len(getattr(node.declarations[0].init, 'elements', [])) > 100):
            return None
        return node
    def visit_FunctionDeclaration(self, node):
        # We keep the function declarations, as some of them might still be used.
        return node

def deobfuscate(js_code):
    try: ast = esprima.parse(js_code, {'comment': True, 'tolerant': True})
    except Exception as e: print(f"Error parsing JavaScript: {e}"); return ""

    # 1. Resolve all calls using the primed context
    resolver = ContextualResolver(ast)
    ast = resolver.visit(ast)

    # 2. Simplify expressions (e.g. "Hello " + "Internet User")
    simplifier = ExpressionSimplifier()
    ast = simplifier.visit(ast)

    # 3. Clean up all the now-dead code (decoders, string arrays)
    cleaner = FinalCleanup()
    ast = cleaner.visit(ast)

    generated_code = escodegen.generate(ast, {'comment': False})
    return jsbeautifier.beautify(generated_code)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='A Python script to deobfuscate JavaScript code.')
    parser.add_argument('input_file', type=str, help='The path to the obfuscated JavaScript file.')
    parser.add_argument('output_file', type=str, help='The path to write the deobfuscated code to.')
    args = parser.parse_args()
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f: obfuscated_code = f.read()
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}"); return

    deobfuscated_code = deobfuscate(obfuscated_code)

    # No report needed for the final clean version
    with open(args.output_file, 'w', encoding='utf-8') as f: f.write(deobfuscated_code)
    print(f"Deobfuscated code written to {args.output_file}")

if __name__ == '__main__':
    main()
